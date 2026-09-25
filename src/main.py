"""Orchestrator: collect -> filter -> score -> AI -> render pipeline."""

import argparse
import re
import json
import time
import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

from src.collectors.base import EventRecord
from src.collectors.real_search import RealSearchCollector
from src.filters.dedup import Deduplicator
from src.filters.quality import QualityFilter
from src.filters.scorer import Scorer
from src.render.markdown_weekly import MarkdownRenderer

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    """Load all YAML config files and merge into one dict."""
    config: dict = {}
    for filename in ["sources.yml", "keywords.yml", "quality.yml"]:
        path = ROOT / "config" / filename
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            config.update(data)
    return config


# --- Semiconductor Equipment domain keyword -> category mapping ---
EVENTS_CATEGORY: dict[str, list[str]] = {
    "#lithography": [
        "EUV", "High-NA", "DUV", "lithography", "光刻", "光刻机", "ASML",
        "TWINSCAN", "EXE", "NXE", "NXT", "Canon", "Nikon", "FPA",
        "NIL", "nanoimprint", "mask", "reticle", "pellicle",
        "anamorphic", "overlay", "套刻", "numerical aperture",
        "resolution enhancement", "multi-patterning", "SADP", "SAQP",
        "极紫外", "浸没式", "ArF", "KrF", "光子掩模",
    ],
    "#etch": [
        "etch", "刻蚀", "蚀刻", "plasma", "RIE", "DRIE", "ICP", "CCP",
        "Lam Research", "Kiyo", "Flex", "TEL", "Tactras",
        "AMEC", "中微", "刻蚀机",
        "HAR", "high aspect ratio", "ALE", "atomic layer etch",
        "selective etch", "nanosheet release", "Bosch process",
        "descum", "ashing", "sidewall passivation",
        "conductor etch", "dielectric etch",
    ],
    "#deposition": [
        "CVD", "PVD", "ALD", "deposition", "薄膜沉积", "沉积",
        "PECVD", "HDPCVD", "SACVD", "EPI", "MOCVD", "epitaxy",
        "Applied Materials", "Endura", "Centura", "Producer",
        "ASM International", "ASM", "Triase", "Telius",
        "Piotech", "拓荆科技",
        "precursor", "前驱体", "conformal", "gap fill",
        "step coverage", "high-k", "metal gate", "barrier layer",
        "low-k dielectric", "sputtering",
    ],
    "#cmp": [
        "CMP", "chemical mechanical", "planarization", "平坦化", "抛光",
        "Applied Materials", "Reflexion", "Ebara", "荏原",
        "Hwatsing", "华海清科",
        "copper CMP", "tungsten CMP", "oxide CMP", "STI CMP",
        "polishing pad", "slurry", "dishing", "erosion",
        "end-point detection", "post-CMP cleaning",
    ],
    "#metrology": [
        "inspection", "metrology", "量检测", "检测", "量测",
        "KLA", "科磊", "39xx", "29xx", "eScan", "Surfscan",
        "CD-SEM", "critical dimension", "overlay metrology",
        "scatterometry", "OCD", "X-ray", "review SEM",
        "bright-field", "dark-field", "e-beam",
        "AI defect classification", "yield management",
        "Skyverse", "中科飞测",
        "film thickness", "particle detection",
        "缺陷检测", "膜厚",
    ],
    "#cleaning": [
        "cleaning", "清洗", "single wafer", "batch", "wet bench",
        "ACM Research", "盛美上海", "ACM",
        "megasonic", "SAPS", "TEBO", "brush cleaning",
        "wet etch", "wet strip", "RCA clean",
        "particle removal", "metal contamination",
        "兆声波", "槽式清洗",
    ],
    "#thermal_implant": [
        "RTP", "rapid thermal", "furnace", "diffusion", "热处理",
        "ion implant", "ion implantation", "离子注入",
        "annealing", "laser annealing", "退火",
        "doping", "dopant activation", "wafer oxidation",
        "Axcelis", "Vantage", "beamline",
        "热处理设备", "扩散炉",
    ],
    "#packaging_test": [
        "ATE", "test equipment", "测试机", "探针", "prober",
        "Teradyne", "Advantest", "爱德万", "泰瑞达",
        "handler", "分选机",
        "dicing", "划片", "grinding", "thinning", "减薄",
        "DISCO", "迪思科", "die bonder", "固晶",
        "wire bonder", "键合机",
        "封装测试", "OSAT",
    ],
    "#china_equip": [
        "北方华创", "NAURA", "中微公司", "AMEC",
        "盛美上海", "ACM Research", "拓荆科技", "Piotech",
        "华海清科", "Hwatsing", "芯源微", "Kingsemi",
        "中科飞测", "Skyverse",
        "国产替代", "自主可控", "国产化",
        "设备国产化率", "去美化",
        "实体清单", "出口管制", "上海微电子",
        "SMEE", "28nm 国产",
        "设备验证", "产线导入",
        "国产零部件", "射频电源国产化",
        "中国半导体设备", "国产设备突破",
    ],
    "#equip_supplychain": [
        "equipment lead time", "设备交期",
        "export control", "BIS", "entity list", "CHIPS Act",
        "RF generator", "RF power", "射频电源",
        "vacuum pump", "Edwards", "Pfeiffer",
        "Zeiss", "蔡司", "光学",
        "MKS Instruments", "Brooks",
        "gas panel", "quartz", "ceramic parts",
        "O-ring", "seal", "valve",
        "设备零部件", "供应链安全",
        "设备走私", "中转贸易",
        "semiconductor equipment ban", "Dutch export",
        "日本设备管制", "荷兰出口管制",
    ],
}


def _auto_categorize(record: EventRecord, config: dict) -> list[str]:
    """Auto-classify based on title keyword matching (word-boundary for ASCII, substring for CJK)."""
    text = (record.title or "").lower()
    category_mapping = config.get("category_mapping", {})
    matched: list[str] = []
    for cat_id, keywords in category_mapping.items():
        for kw in keywords:
            if _kw_match((kw or "").lower(), text):
                cat_name = cat_id
                for cc in config.get("categories", []):
                    if cc.get("id") == cat_id:
                        cat_name = cc.get("name", cat_id)
                        break
                matched.append(cat_name)
                break
    return matched


def _kw_match(kw: str, text: str) -> bool:
    if not kw:
        return False
    if any("\u4e00" <= ch <= "\u9fff" for ch in kw):
        return kw in text
    return re.search(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text) is not None

def _merge_records(records: list[EventRecord]) -> list[EventRecord]:
    """Merge records with same event_id, combining citation chains."""
    merged: dict[str, EventRecord] = {}
    for r in records:
        if r.event_id in merged:
            existing = merged[r.event_id]
            existing_keys = {c.source_key for c in existing.citations}
            for c in r.citations:
                if c.source_key not in existing_keys:
                    existing.citations.append(c)
            if r.description and len(r.description) > len(existing.description or ""):
                existing.description = r.description
        else:
            merged[r.event_id] = r
    return list(merged.values())


def _generate_cn_titles(records: list[EventRecord]) -> None:
    """Generate Chinese titles for ALL event records via LLM batch translation.

    Strategy: LLM translates all events in batches (20 per call).
    Skipped entirely when no LLM key is configured (keyword substitution
    produced mixed-language garbage).
    """
    try:
        from src.ai.llm_client import LLMClient
        _llm_client = LLMClient()
    except Exception:
        _llm_client = None
    if _llm_client is None:
        # No LLM key configured — leave titles untranslated instead of
        # emitting mixed-language keyword substitutions.
        print("[CN translate] No LLM key — skipping Chinese title generation")
        return

    import re

    # --- LLM batch translation for ALL events ---
    try:
        from src.ai.llm_client import LLMClient
        client = LLMClient()
    except Exception:
        print("  [CN translate] No LLM key found -- using keyword-only fallback")
        return

    BATCH_SIZE = 20
    id_to_cn: dict[str, str] = {}
    all_records = [r for r in records if r.title.strip()]

    for batch_start in range(0, len(all_records), BATCH_SIZE):
        batch = all_records[batch_start:batch_start + BATCH_SIZE]
        lines = [f"{j+1}. {r.title}" for j, r in enumerate(batch)]
        prompt = (
            "Translate these semiconductor equipment news headlines into concise, fluent Chinese.\n"
            "Rules: keep technical acronyms (EUV/High-NA/DUV/GAA/HBM/CoWoS/ALD/CVD/PVD/CCP/ICP) as-is.\n"
            "Return exactly one line per number, format: N. Chinese translation\n\n"
            + "\n".join(lines)
        )

        for attempt in range(3):
            try:
                import time
                if attempt > 0:
                    time.sleep(60)  # wait for rate-limit window to reset
                result = client.chat(
                    "You are a semiconductor equipment industry translator. Translate English news headlines "
                    "into fluent, concise Chinese. Preserve technical acronyms. Output format: "
                    "N. Chinese translation \u2014 one numbered line per headline, no extra text.",
                    prompt, temperature=0.1,
                )
                for line in result.strip().split("\n"):
                    line = line.strip()
                    parts = line.split(". ", 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        idx = int(parts[0]) - 1
                        if 0 <= idx < len(batch):
                            id_to_cn[batch[idx].event_id] = parts[1].strip()
                break
            except Exception as e:
                print(f"  [CN translate] Batch {batch_start // BATCH_SIZE + 1} attempt {attempt + 1} failed: {str(e)[:80]}")
                if attempt == 2:
                    print(f"  [CN translate] Batch {batch_start // BATCH_SIZE + 1} exhausted retries, using keyword preprocess")
        import time
        time.sleep(2)  # rate limiting guard

    for r in records:
        if r.event_id in id_to_cn and id_to_cn[r.event_id]:
            r.title_cn = id_to_cn[r.event_id]

    print(f"  [CN translate] LLM translated {len(id_to_cn)}/{len(all_records)} titles")


def run_weekly(config: dict):
    """Full weekly pipeline: collect from all Tier 1 + Tier 2 sources."""
    print(f"[Weekly] Starting pipeline -- {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    records: list[EventRecord] = []

    sources_cfg = config.get("sources", {})
    enabled_sources = {k: v for k, v in sources_cfg.items() if v.get("enabled", True)}

    print(f"[Weekly] Collecting from {len(enabled_sources)} sources...")

    for source_key, source_cfg in enabled_sources.items():
        try:
            collector = RealSearchCollector(config, source_key)
            collector.gh_token = os.environ.get("GH_TOKEN", "")
            items = collector.collect()
            for item in items:
                item.categories = _auto_categorize(item, config)
            records.extend(items)
            if items:
                print(f"  [{source_key}] {len(items)} items -- {source_cfg.get('name', source_key)}")
        except Exception as e:
            print(f"  [{source_key}] FAILED: {e}")

    if not records:
        print("[Weekly] No records collected -- check source configuration.")
        return

    # Merge + dedup
    merged = _merge_records(records)
    print(f"[Weekly] Merged: {len(merged)} unique events (from {len(records)} raw)")

    qf = QualityFilter(config)
    filtered, qstats = qf.filter(merged)
    print(f"[Weekly] Quality filter: {qstats}")
    if not filtered:
        print("[Weekly] No records passed quality filter.")
        return

    dedup = Deduplicator(str(ROOT / "data" / "dedup_state.json"))
    new_records, seen = dedup.deduplicate(filtered)
    print(f"[Weekly] Dedup: {len(new_records)} new / {seen} already seen")

    if not new_records:
        print("[Weekly] All events already seen this cycle.")
        return

    scorer = Scorer(config)
    new_records = scorer.score(new_records)
    new_records.sort(key=lambda r: r.confidence_score, reverse=True)

    grade_counts = {}
    for r in new_records:
        g = r.confidence_grade
        grade_counts[g] = grade_counts.get(g, 0) + 1
    grade_str = ", ".join(f"{k}:{v}" for k, v in sorted(grade_counts.items()))
    print(f"[Weekly] Filtered+Scored: {len(new_records)} events -- {grade_str}")

    # Generate Chinese titles (LLM batch translation with rule-based fallback)
    _generate_cn_titles(new_records)
    cn_count = sum(1 for r in new_records if r.title_cn)
    print(f"[Weekly] CN titles generated: {cn_count}/{len(new_records)}")

    # AI deep analysis
    deep_analysis = ""
    try:
        from src.ai.llm_client import LLMClient
        from src.ai.deep_analyzer import DeepAnalyzer

        client = LLMClient()
        analyzer = DeepAnalyzer(client, ROOT / "prompts")
        top_n = min(len(new_records), 15)
        deep_analysis = analyzer.analyze(new_records, top_n=top_n)
        print(f"[Weekly] AI deep analysis generated ({len(deep_analysis)} chars)")
    except Exception as e:
        print(f"[Weekly] AI skipped (will render data-only report): {e}")

    # Render
    category_order = [c.get("name") for c in config.get("categories", [])]
    renderer = MarkdownRenderer(str(ROOT / "output"), category_order=category_order)
    stats = {
        "本周采集": len(records),
        "历史已见": seen,
        "质量过滤排除": sum(qstats.values()) - qstats["kept"] - qstats["fallback_excluded"],
        "占位骨架排除": qstats["fallback_excluded"],
        "新事件": len(new_records),
        "可信度分布": grade_str,
        "独立生态覆盖": _eco_coverage(new_records),
    }
    renderer.render_weekly_report(new_records, deep_analysis=deep_analysis, stats=stats)
    dedup.save()

    print(f"[Weekly] Done -- report written to output/")
    print(f"[Weekly] Top event: {new_records[0].title[:80] if new_records else 'N/A'}")


def _eco_coverage(records: list[EventRecord]) -> str:
    ecosystems: set[str] = set()
    for r in records:
        for c in r.citations:
            ecosystems.add(c.ecosystem)
    return f"{len(ecosystems)} ecosystems: {', '.join(sorted(ecosystems)[:8])}"


# ---- CLI entry ----

def main():
    parser = argparse.ArgumentParser(description="Weekly domain intelligence digest")
    parser.add_argument(
        "--mode", choices=["weekly", "daily"], default="weekly",
        help="Run mode: weekly (full pipeline) or daily (Tier 1 only)",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))

    config = load_config()
    print(f"[Main] Mode: {args.mode} | Sources: {len(config.get('sources', {}))}")

    if args.mode == "weekly":
        run_weekly(config)
    else:
        print("[Main] Daily mode not yet configured -- use weekly.")


if __name__ == "__main__":
    main()
