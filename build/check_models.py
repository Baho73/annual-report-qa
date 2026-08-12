# -*- coding: utf-8 -*-
"""Проверка доступности и цен моделей на OpenRouter."""
import json

import requests

KEY = json.load(open(r"D:\Python\hh_answer\user_profile.json", encoding="utf-8"))["openrouter_api_key"]
WANT = ["anthropic/claude-opus-5-fast", "anthropic/claude-opus-5",
        "anthropic/claude-fable-5", "openai/gpt-5.5-pro", "anthropic/claude-sonnet-5"]

r = requests.get("https://openrouter.ai/api/v1/models",
                 headers={"Authorization": f"Bearer {KEY}"}, timeout=60)
r.raise_for_status()
data = r.json()["data"]
by_id = {m["id"]: m for m in data}
for w in WANT:
    m = by_id.get(w)
    if not m:
        near = [i for i in by_id if w.split("/")[-1][:12] in i]
        print(f"{w}: НЕТ. похожие: {near[:6]}")
        continue
    p = m["pricing"]
    mods = m.get("architecture", {}).get("input_modalities")
    print(f"{w}: ctx={m.get('context_length')} in=${float(p['prompt'])*1e6:.2f}/M "
          f"out=${float(p['completion'])*1e6:.2f}/M img={p.get('image')} mod={mods}")
