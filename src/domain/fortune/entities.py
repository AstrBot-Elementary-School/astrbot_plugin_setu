"""每日运势只保存抽取结果和图片关联。"""

import random
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class FortuneRecord:
    id: int
    session_id: str
    user_id: str
    date_str: str
    star_count: int
    setu_history_id: int | None = None


@dataclass(frozen=True, slots=True)
class FortuneGenerationRequest:
    user_id: str
    username: str
    date_str: str
    session_id: str

    @classmethod
    def for_today(cls, user_id, username, session_id):
        return cls(user_id, username, date.today().isoformat(), session_id)


class FortuneWeights:
    def calculate_star(self):
        return random.choices(
            range(8), weights=(0.1, 0.15, 0.2, 0.25, 0.15, 0.12, 0.07, 0.005)
        )[0]
