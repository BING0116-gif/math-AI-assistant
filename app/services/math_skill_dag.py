import os
import yaml


class MathSkillDAG:
    def __init__(self, yaml_path: str = None):
        if yaml_path is None:
            yaml_path = os.path.join(
                os.path.dirname(__file__),
                "..", "data", "math_skill_graph.yml",
            )
        with open(yaml_path, "r", encoding="utf-8") as f:
            self._graph = yaml.safe_load(f)

    def get_skill(self, code: str) -> dict:
        return self._graph.get(code, {})

    def get_prerequisites(self, code: str) -> list:
        return self._graph.get(code, {}).get("prerequisites", [])

    def get_unlocks(self, code: str) -> list:
        unlocks = []
        for key, node in self._graph.items():
            if code in node.get("prerequisites", []):
                unlocks.append(key)
        return unlocks

    def can_learn(self, code: str, mastered_skills: set) -> bool:
        prereqs = self.get_prerequisites(code)
        return all(p in mastered_skills for p in prereqs) if prereqs else True

    def get_next_unlockable(
        self, mastered_skills: set, learning_skills: set
    ) -> list:
        unlockable = []
        for code, node in self._graph.items():
            if code in mastered_skills or code in learning_skills:
                continue
            prereqs = node.get("prerequisites", [])
            if all(p in mastered_skills for p in prereqs):
                unlockable.append({"code": code, "node": node})
        return unlockable

    def get_all_skill_codes(self) -> list:
        return list(self._graph.keys())