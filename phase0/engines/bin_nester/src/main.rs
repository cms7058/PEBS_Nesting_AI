//! bin_nester —— 固定尺寸板材的二维异形装箱求解器(方案乙)。
//!
//! 基于 jagua-rs 的 BPP 模型与碰撞引擎(CDE),实现构造式 FFD + 底左填充:
//! 零件按面积降序、按需求量展开,逐件在已开板上找底左可行位;放不下则从库存开新板。
//! 容器边界已注册为 hazard,`detect_poly_collision` 一次同时判「重叠 + 越界」。
//!
//! 输入/输出为 jagua-rs BPP 的标准 JSON(ExtBPInstance / ExtBPSolution)。

use std::f32::consts::PI;
use std::fs;
use std::path::PathBuf;

use anyhow::Result;
use clap::Parser;
use serde::Serialize;

use jagua_rs::collision_detection::hazards::filter::NoFilter;
use jagua_rs::collision_detection::CDEConfig;
use jagua_rs::entities::Instance;
use jagua_rs::geometry::geo_traits::TransformableFrom;
use jagua_rs::geometry::fail_fast::SPSurrogateConfig;
use jagua_rs::geometry::primitives::SPolygon;
use jagua_rs::geometry::{DTransformation, Transformation};
use jagua_rs::io::import::Importer;
use jagua_rs::probs::bpp::entities::{BPInstance, BPLayoutType, BPPlacement, BPProblem};
use jagua_rs::probs::bpp::io::ext_repr::ExtBPInstance;
use jagua_rs::probs::bpp::io::import_instance;
use jagua_rs::Instant;

/// 输出:带几何的出料结果(便于前端精确渲染各张板)。
#[derive(Serialize)]
struct PlacedOut {
    item_id: usize,
    points: Vec<(f32, f32)>,
}
#[derive(Serialize)]
struct SheetOut {
    bin_id: usize,
    width: f32,
    height: f32,
    density: f32,
    items: Vec<PlacedOut>,
}
#[derive(Serialize)]
struct SolutionOut {
    density: f32,
    bins_used: usize,
    placed: usize,
    shortfall: usize,
    placed_counts: Vec<usize>, // 按 item_id 已排数量
    sheets: Vec<SheetOut>,
}

#[derive(Parser)]
struct Cli {
    /// 输入 JSON(ExtBPInstance)
    #[arg(short, long)]
    input: PathBuf,
    /// 输出 JSON(ExtBPSolution)
    #[arg(short, long)]
    output: PathBuf,
    /// 底左扫描步长(mm)。留空则按容器尺寸自动取(更细=更紧但更慢)。
    #[arg(short, long)]
    step: Option<f32>,
    /// 总时限(秒),多起点搜索在此预算内尝试不同排序取最优。
    #[arg(short, long, default_value_t = 15)]
    time: u64,
}

const ROTATIONS: [f32; 4] = [0.0, PI / 2.0, PI, 3.0 * PI / 2.0];

fn cde_config() -> CDEConfig {
    CDEConfig {
        quadtree_depth: 4,
        cd_threshold: 16,
        item_surrogate_config: SPSurrogateConfig {
            n_pole_limits: [(64, 0.0), (16, 0.8), (8, 0.9)],
            n_ff_poles: 1,
            n_ff_piers: 0,
        },
    }
}

fn auto_step(bbox: jagua_rs::geometry::primitives::Rect, step: f32) -> f32 {
    if step > 0.0 {
        step
    } else {
        // 步长:更细=更紧但更慢。配天际线评分 + 重力下落,细步长明显更紧。
        (bbox.width().min(bbox.height()) / 150.0).clamp(1.0, 12.0)
    }
}

#[inline]
fn feasible_at(
    cde: &jagua_rs::collision_detection::CDEngine,
    buff: &mut SPolygon,
    item_shape: &SPolygon,
    rot: f32,
    tx: f32,
    ty: f32,
) -> bool {
    let t = Transformation::default().rotate_translate(rot, (tx, ty));
    buff.transform_from(item_shape, &t);
    !cde.detect_poly_collision(buff, &NoFilter)
}

/// 接触式压缩:把已定位的件向左下细步贴合滑动到接触,消除网格/列粗化留下的 mm 级间隙。
fn refine_contact(
    cde: &jagua_rs::collision_detection::CDEngine,
    bbox: jagua_rs::geometry::primitives::Rect,
    item_shape: &SPolygon,
    rot: f32,
    mut tx: f32,
    mut ty: f32,
    fine: f32,
) -> (f32, f32) {
    let mut buff = item_shape.clone();
    loop {
        let mut moved = false;
        // 下滑到接触
        while ty - fine >= bbox.y_min - 1e-6 && feasible_at(cde, &mut buff, item_shape, rot, tx, ty - fine) {
            ty -= fine;
            moved = true;
        }
        // 左滑到接触
        while tx - fine >= bbox.x_min - 1e-6 && feasible_at(cde, &mut buff, item_shape, rot, tx - fine, ty) {
            tx -= fine;
            moved = true;
        }
        if !moved {
            break;
        }
    }
    (tx, ty)
}

/// 重力下落式真·底左 + 接触式压缩:网格粗定位选最低天际线,再贴合滑动到接触。
fn bottom_left(
    cde: &jagua_rs::collision_detection::CDEngine,
    bbox: jagua_rs::geometry::primitives::Rect,
    item_shape: &SPolygon,
    step: f32,
) -> Option<DTransformation> {
    let mut buff = item_shape.clone();
    let mut best: Option<(f32, f32, f32, f32)> = None; // (y_max, x_min, rot, ...) → 存 rot/tx/ty

    // 列扫描放粗(快),靠 refine 贴合补回紧度
    let tx_step = step * 2.5;
    let mut best_pos: Option<(f32, f32, f32)> = None; // (rot, tx, ty)
    let mut tx = bbox.x_min;
    while tx <= bbox.x_max {
        for &rot in ROTATIONS.iter() {
            let mut ty = bbox.y_min;
            while ty <= bbox.y_max {
                if feasible_at(cde, &mut buff, item_shape, rot, tx, ty) {
                    // 评分键:件顶 y_max 最低(最低天际线),再 x_min 靠左
                    let (ymax, xmin) = (buff.bbox.y_max, buff.bbox.x_min);
                    let better = match &best {
                        None => true,
                        Some((by, bx, _, _)) => ymax < *by - 1e-6 || (ymax <= *by + 1e-6 && xmin < *bx),
                    };
                    if better {
                        best = Some((ymax, xmin, rot, 0.0));
                        best_pos = Some((rot, tx, ty));
                    }
                    break; // 该(tx,rot)已落到最低
                }
                ty += step;
            }
        }
        tx += tx_step;
    }

    best_pos.map(|(rot, tx, ty)| {
        let fine = (step / 4.0).max(0.5);
        let (rx, ry) = refine_contact(cde, bbox, item_shape, rot, tx, ty, fine);
        DTransformation::new(rot, (rx, ry))
    })
}

fn find_placement(prob: &BPProblem, item_id: usize, step: f32) -> Option<BPPlacement> {
    let item = prob.instance.item(item_id);
    let item_shape = item.shape_cd.as_ref();

    // 1) 优先填已开板(first-fit,促进装满)
    for (lkey, layout) in prob.layouts.iter() {
        let bbox = layout.container.outer_cd.bbox;
        if let Some(dt) = bottom_left(layout.cde(), bbox, item_shape, auto_step(bbox, step)) {
            return Some(BPPlacement { layout_id: BPLayoutType::Open(lkey), item_id, d_transf: dt });
        }
    }

    // 2) 已开板放不下 → 从有库存的板型开新板
    for bin in prob.instance.bins() {
        if prob.bin_stock_qtys[bin.id] > 0 {
            let layout = jagua_rs::entities::Layout::new(bin.container.clone());
            let bbox = layout.container.outer_cd.bbox;
            if let Some(dt) = bottom_left(layout.cde(), bbox, item_shape, auto_step(bbox, step)) {
                return Some(BPPlacement {
                    layout_id: BPLayoutType::Closed { bin_id: bin.id },
                    item_id,
                    d_transf: dt,
                });
            }
        }
    }
    None
}

/// 一次构造:按给定顺序放置全部需求件,返回 (problem, 未排件数)。
fn solve_once(instance: BPInstance, order: &[usize], step: f32) -> (BPProblem, usize) {
    let mut prob = BPProblem::new(instance);
    let mut shortfall = 0usize;
    for &item_id in order {
        match find_placement(&prob, item_id, step) {
            Some(p) => {
                prob.place_item(p);
            }
            None => shortfall += 1,
        }
    }
    (prob, shortfall)
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    let epoch = Instant::now();

    let ext: ExtBPInstance = serde_json::from_str(&fs::read_to_string(&cli.input)?)?;
    let importer = Importer::new(cde_config(), Some(0.001), None, Some((0.01, 0.01)));
    let instance = import_instance(&importer, &ext)?;

    let n_items = instance.items.len();
    let step = cli.step.unwrap_or(0.0);

    // 各件 bbox 尺寸,用于不同排序键
    let dims: Vec<(f32, f32, f32)> = (0..n_items)
        .map(|id| {
            let bb = instance.item(id).shape_cd.bbox;
            (bb.width() * bb.height(), bb.height(), bb.width()) // (面积, 高, 宽)
        })
        .collect();
    let demand: Vec<usize> = instance.items.iter().map(|(_, q)| *q).collect();

    // 候选排序键:面积降序 / 高降序 / 宽降序 / 长边降序 + 随机扰动
    let make_order = |key: usize| -> Vec<usize> {
        let mut ids: Vec<usize> = (0..n_items).collect();
        match key {
            0 => ids.sort_by(|&a, &b| dims[b].0.partial_cmp(&dims[a].0).unwrap()),
            1 => ids.sort_by(|&a, &b| dims[b].1.partial_cmp(&dims[a].1).unwrap()),
            2 => ids.sort_by(|&a, &b| dims[b].2.partial_cmp(&dims[a].2).unwrap()),
            _ => ids.sort_by(|&a, &b| {
                let la = dims[a].1.max(dims[a].2);
                let lb = dims[b].1.max(dims[b].2);
                lb.partial_cmp(&la).unwrap()
            }),
        };
        ids.iter()
            .flat_map(|&id| std::iter::repeat(id).take(demand[id]))
            .collect()
    };

    // 多起点:在时限内尝试不同排序,保留密度最高的解
    let budget = std::time::Duration::from_secs(cli.time);
    let wall = std::time::Instant::now();
    let mut best: Option<(BPProblem, usize)> = None;
    let mut tried = 0;
    for key in 0..4 {
        // 投影式停:仅当预计下一起点能在预算内完成时才继续(大实例只跑1起点,小实例跑多起点)
        if tried > 0 {
            let elapsed = wall.elapsed().as_secs_f64();
            let avg = elapsed / tried as f64;
            if elapsed + avg > budget.as_secs_f64() {
                break;
            }
        }
        let order = make_order(key);
        let (p, sf) = solve_once(instance.clone(), &order, step);
        tried += 1;
        let dens = p.density();
        eprintln!("[bin_nester] 起点{key}: 利用率 {:.1}% 用板 {} 缺口 {}",
            dens * 100.0, p.bin_used_qtys().sum::<usize>(), sf);
        let keep = match &best {
            None => true,
            Some((bp, bsf)) => sf < *bsf || (sf == *bsf && dens > bp.density()),
        };
        if keep {
            best = Some((p, sf));
        }
    }

    let (prob, shortfall) = best.expect("至少一次构造");
    let bins_used: usize = prob.bin_used_qtys().sum();
    eprintln!(
        "[bin_nester] ★最优: 已放置 {} 件，用板 {} 张，总利用率 {:.1}%，未排下 {} 件(试 {} 起点)",
        prob.n_placed_items(), bins_used, prob.density() * 100.0, shortfall, tried
    );

    // 组装带几何的输出
    let sheets: Vec<SheetOut> = prob
        .layouts
        .values()
        .map(|layout| {
            let bbox = layout.container.outer_cd.bbox;
            let items = layout
                .placed_items
                .values()
                .map(|pi| PlacedOut {
                    item_id: pi.item_id,
                    points: pi.shape.vertices.iter().map(|p| (p.0, p.1)).collect(),
                })
                .collect();
            SheetOut {
                bin_id: layout.container.id,
                width: bbox.width(),
                height: bbox.height(),
                density: layout.placed_item_area(&prob.instance) / layout.container.area(),
                items,
            }
        })
        .collect();

    let out = SolutionOut {
        density: prob.density(),
        bins_used,
        placed: prob.n_placed_items(),
        shortfall,
        placed_counts: prob.item_placed_qtys().collect(),
        sheets,
    };
    let _ = epoch;
    fs::write(&cli.output, serde_json::to_string(&out)?)?;
    Ok(())
}
