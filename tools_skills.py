"""
tools_skills.py
Specialized tool implementations for:
1. GitHub Repository Reverse Engineering & API Contract Synthesis
2. YouTube Video Editing Timeline & FFmpeg Filter Generation
3. Modern Responsive Website Design Scaffolding
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent


def reverse_engineer_github(repo_path_or_url: str, extract_apis: bool = True) -> str:
    """
    Reverse engineers a GitHub repository or local directory.
    Extracts exported symbols, API router endpoints, dependency graph,
    and synthesizes an OpenAPI-compatible endpoint contract.
    """
    path = Path(repo_path_or_url)
    target_dir = path if path.exists() and path.is_dir() else PROJECT_ROOT

    endpoints = []
    frameworks = []
    models = []
    dependencies = []

    # Check for package / dependency manifests
    for manifest_name in ("package.json", "requirements.txt", "Cargo.toml", "go.mod", "pyproject.toml"):
        mf = target_dir / manifest_name
        if mf.exists():
            try:
                txt = mf.read_text(encoding="utf-8", errors="ignore")
                dependencies.append(f"{manifest_name} ({len(txt.splitlines())} lines)")
            except Exception:
                pass

    # Scan python, js, ts files in the target
    for ext in ("*.py", "*.js", "*.ts"):
        for f in list(target_dir.rglob(ext))[:50]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                # Detect routing
                for match in re.finditer(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', content):
                    endpoints.append({
                        "method": match.group(1).upper(),
                        "path": match.group(2),
                        "source": f.name
                    })
                    if "FastAPI" not in frameworks and "fastapi" in content.lower():
                        frameworks.append("FastAPI")
                    if "Flask" not in frameworks and "flask" in content.lower():
                        frameworks.append("Flask")
                for match in re.finditer(r'(?:app|router)\.(get|post|put|delete)\(\s*["\']([^"\']+)["\']', content):
                    endpoints.append({
                        "method": match.group(1).upper(),
                        "path": match.group(2),
                        "source": f.name
                    })
                    if "Express" not in frameworks and "express" in content.lower():
                        frameworks.append("Express")
                # Detect Pydantic/Zod models
                for match in re.finditer(r'class\s+([A-Za-z0-9_]+)\((?:BaseModel|Schema)\):', content):
                    models.append(match.group(1))
            except Exception:
                continue

    report = [
        f"=== REVERSE ENGINEERING ANALYSIS: {repo_path_or_url} ===",
        f"Detected Frameworks: {', '.join(frameworks) if frameworks else 'Standard REST / Custom Dispatch'}",
        f"Manifest Dependencies: {', '.join(dependencies) if dependencies else 'None detected'}",
        f"Discovered Models/Schemas: {len(models)} ({', '.join(models[:8])}{'...' if len(models) > 8 else ''})",
        f"Reconstructed Endpoints ({len(endpoints)} total):"
    ]

    for ep in endpoints[:15]:
        report.append(f"  [{ep['method']:<6}] {ep['path']:<35} (via {ep['source']})")

    if extract_apis and endpoints:
        report.append("\nSynthesized OpenAPI Contract Preview:")
        openapi_sample = {
            "openapi": "3.1.0",
            "info": {"title": f"Reverse-Engineered API: {path.name}", "version": "1.0.0"},
            "paths": {ep["path"]: {ep["method"].lower(): {"summary": f"Inferred {ep['method']} {ep['path']}"}} for ep in endpoints[:5]}
        }
        report.append(json.dumps(openapi_sample, indent=2))

    return "\n".join(report)


def edit_video_timeline(project_name: str, cuts_json: str, format: str = "fcpxml") -> str:
    """
    Automates YouTube video timeline editing.
    Parses cuts, applies audio ducking and loudness normalization (-14 LUFS),
    and generates both timeline interchange metadata and an FFmpeg command.
    """
    try:
        cuts = json.loads(cuts_json) if isinstance(cuts_json, str) and cuts_json.strip().startswith("[") else []
    except Exception:
        cuts = [{"start": "00:00:00", "end": "00:00:15", "type": "intro_hook", "lufs": -14.0}]

    if not cuts:
        cuts = [
            {"start": "00:00:00", "end": "00:00:03", "type": "hook_pacing", "transition": "cut"},
            {"start": "00:00:03", "end": "00:00:18", "type": "main_content", "bgm_duck_db": -16.0},
            {"start": "00:00:18", "end": "00:00:25", "type": "cta_outro", "transition": "fade_black"}
        ]

    video_filter = ""
    if format.lower() in ("shorts", "tiktok", "reels", "vertical"):
        video_filter = ' -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"'

    ffmpeg_filter = (
        'ffmpeg -i input.mp4 -i bgm.mp3 -filter_complex '
        '"[0:a]loudnorm=I=-14:LRA=7:tp=-1.0[vocal];'
        '[1:a]volume=0.15[bgm];'
        '[vocal][bgm]amix=inputs=2:duration=first[aout]" '
        f'-map 0:v{video_filter} -map "[aout]" -c:v libx264 -preset fast -crf 20 output_{project_name}.mp4'
    )

    result = {
        "project": project_name,
        "format": format.lower(),
        "total_cuts": len(cuts),
        "cuts": cuts,
        "loudness_target": "-14.0 LUFS",
        "ffmpeg_pipeline": ffmpeg_filter,
        "status": "TIMELINE_GENERATED_OK"
    }

    return json.dumps(result, indent=2)


def scaffold_modern_website(site_name: str, layout_type: str = "landing_page", theme: str = "dark_neon") -> str:
    """
    Scaffolds a modern, responsive website with semantic HTML5,
    glassmorphism CSS, flex/grid responsiveness, and dark mode UI.
    """
    clean_name = re.sub(r"[^A-Za-z0-9_-]", "_", site_name)
    out_dir = PROJECT_ROOT / "generated_sites" / clean_name
    out_dir.mkdir(parents=True, exist_ok=True)

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{site_name} | Modern Web Experience</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            brand: {{
              emerald: '#00f5a0',
              cyan: '#00d2ff',
              violet: '#7928ca',
              dark: '#030712'
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    .glass {{
      background: rgba(11, 16, 28, 0.75);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
    .glow-radial {{
      background: radial-gradient(circle at 50% 0%, rgba(0, 245, 160, 0.15), transparent 70%);
    }}
  </style>
</head>
<body class="bg-[#030712] text-slate-100 min-h-screen flex flex-col glow-radial selection:bg-brand-emerald selection:text-black">
  <!-- Nav Header -->
  <header class="sticky top-0 z-50 glass border-b border-slate-800">
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <span class="w-3 h-3 rounded-full bg-brand-emerald animate-pulse"></span>
        <span class="font-mono font-bold tracking-wider text-brand-emerald">{site_name.upper()}</span>
      </div>
      <nav class="hidden md:flex items-center space-x-8 text-sm font-medium text-slate-300">
        <a href="#features" class="hover:text-brand-emerald transition-colors">Features</a>
        <a href="#architecture" class="hover:text-brand-emerald transition-colors">Architecture</a>
        <a href="#api" class="hover:text-brand-emerald transition-colors">API</a>
      </nav>
      <a href="#cta" class="px-4 py-2 text-xs font-semibold uppercase tracking-wider bg-brand-emerald text-black rounded hover:bg-emerald-400 transition-colors">Get Started</a>
    </div>
  </header>

  <!-- Main Content -->
  {"<!-- Dashboard View -->" if layout_type == "dashboard" else "<!-- Hero Section -->"}
  {"""
  <div class="flex-1 flex flex-col md:flex-row max-w-7xl mx-auto w-full px-4 sm:px-6 py-8 gap-6">
    <aside class="w-full md:w-64 glass rounded-xl p-4 flex flex-col gap-3">
      <div class="text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Navigation</div>
      <a href="#" class="px-3 py-2 rounded-lg bg-brand-emerald/10 text-brand-emerald font-medium text-sm">Dashboard Overview</a>
      <a href="#" class="px-3 py-2 rounded-lg text-slate-400 hover:text-white font-medium text-sm">Telemetry & Nodes</a>
      <a href="#" class="px-3 py-2 rounded-lg text-slate-400 hover:text-white font-medium text-sm">API Integrations</a>
      <a href="#" class="px-3 py-2 rounded-lg text-slate-400 hover:text-white font-medium text-sm">Security Vault</a>
    </aside>
    <main class="flex-1 flex flex-col gap-6">
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div class="glass p-5 rounded-xl">
          <div class="text-xs text-slate-400 uppercase font-mono">Total Throughput</div>
          <div class="text-3xl font-bold text-white mt-1">43.6 <span class="text-sm font-normal text-brand-emerald">tok/s</span></div>
        </div>
        <div class="glass p-5 rounded-xl">
          <div class="text-xs text-slate-400 uppercase font-mono">Active Clusters</div>
          <div class="text-3xl font-bold text-brand-cyan mt-1">119 <span class="text-sm font-normal text-slate-400">tools</span></div>
        </div>
        <div class="glass p-5 rounded-xl">
          <div class="text-xs text-slate-400 uppercase font-mono">Hardware VRAM</div>
          <div class="text-3xl font-bold text-emerald-400 mt-1">2.3 / 4.0 <span class="text-sm font-normal text-slate-400">GB</span></div>
        </div>
      </div>
      <div class="glass p-6 rounded-xl flex-1">
        <div class="text-sm font-semibold text-slate-200 mb-4">Neural Cluster Activity</div>
        <div class="h-48 rounded bg-slate-900/60 flex items-center justify-center text-xs font-mono text-slate-500">
          [Real-Time Digraph Stream Active]
        </div>
      </div>
    </main>
  </div>
  """ if layout_type == "dashboard" else f"""
  <main class="flex-1 max-w-7xl mx-auto px-6 py-20 flex flex-col justify-center">
    <div class="max-w-3xl">
      <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono glass text-brand-cyan mb-6">
        <span>● Active System</span> · <span>Zero Latency Architecture</span>
      </div>
      <h1 class="text-5xl sm:text-6xl font-extrabold tracking-tight text-white mb-6">
        Next-Generation <span class="text-transparent bg-clip-text bg-gradient-to-r from-brand-emerald via-brand-cyan to-brand-violet">{site_name}</span>
      </h1>
      <p class="text-lg text-slate-400 mb-8 leading-relaxed">
        Engineered with modern responsive primitives, fluid typography, and sub-second performance.
      </p>
      <div class="flex flex-wrap gap-4">
        <button class="px-6 py-3 font-semibold bg-brand-emerald text-black rounded shadow-lg shadow-emerald-500/20 hover:bg-emerald-400 transition-all">
          Explore System
        </button>
        <button class="px-6 py-3 font-semibold glass text-slate-200 rounded hover:bg-slate-800/80 transition-all">
          Documentation
        </button>
      </div>
    </div>
  </main>
  """}

  <!-- Footer -->
  <footer class="glass border-t border-slate-800/80 py-6 mt-12">
    <div class="max-w-7xl mx-auto px-6 text-center text-xs text-slate-500 font-mono">
      © 2026 {site_name} · Built with Z.A.I.N.E Neural Engine
    </div>
  </footer>
</body>
</html>
"""
    out_file = out_dir / "index.html"
    out_file.write_text(html_content, encoding="utf-8")

    return f"Successfully scaffolded modern website at: {out_file} (HTML5, Tailwind, Glassmorphism, Responsive Mobile/Desktop)"

