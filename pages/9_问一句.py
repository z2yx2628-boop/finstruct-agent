"""问一句（全屏版）：与每个页面右下角的悬浮按钮相同，只是占满整页。"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ask import INTENTS  # noqa: E402
from src.ask_view import ask_box  # noqa: E402
from src.ui import page_header  # noqa: E402

page_header("问一句", ":material/forum:", "用一句话问系统：它会选一个工具作答，并告诉你用了哪些数据、怎么得出的。",
            about="**它怎么工作**：先用规则识别问题里的企业、产品和数字，归入固定的几类问题；规则判断不了时，"
                  "才请大模型在同一张工具清单里选一类（只做分类，不写答案）。答案里的每个数字都来自与其他页面相同的计算，"
                  "并标明性质：已发生事件（事实）、风险敞口、模型预警或情景假设。超出范围的问题会直接说明不支持。  \n"
                  "**能回答的问题**：" + "；".join(f"{v[0]}（{v[1]}）" for v in INTENTS.values()) + "。  \n"
                  "每个页面右下角的圆形按钮 💬 也能随时提问，按钮可以拖动。")
ask_box("ask")
