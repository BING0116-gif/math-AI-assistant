#!/usr/bin/env bash
set -e
python3 -m pip install -r requirements.txt
python3 db.py init
python3 db.py import sample_questions.json
python3 -m streamlit run app.py
