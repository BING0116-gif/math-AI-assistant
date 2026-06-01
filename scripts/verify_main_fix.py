import sys, os
sys.path.insert(0, os.getcwd())
from main import app, agent
print("main.py import OK")
print("agent has behavior_tracker:", hasattr(agent, "_behavior_tracker"))
print("agent has persistence:", hasattr(agent, "_persistence_facade"))
print("agent has llm:", hasattr(agent, "_llm"))