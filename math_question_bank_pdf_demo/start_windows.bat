@echo off
python -m pip install -r requirements.txt
python db.py init
python db.py import sample_questions.json
python -m streamlit run app.py
