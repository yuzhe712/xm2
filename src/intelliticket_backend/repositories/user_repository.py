from __future__ import annotations

from intelliticket_backend.schemas.users import User, UserRole, hash_password

_BUILTIN_USERS: dict[str, User] = {
    "zhangsan": User(
        user_id="zhangsan",
        name="张三",
        role=UserRole.OPERATOR,
        password_hash=hash_password("zhangsan123"),
        dingtalk_user_id=None,
    ),
    "lisi": User(
        user_id="lisi",
        name="李四",
        role=UserRole.OPERATOR,
        password_hash=hash_password("lisi123"),
        dingtalk_user_id=None,
    ),
    "wangwu": User(
        user_id="wangwu",
        name="王五",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("wangwu123"),
        dingtalk_user_id=None,
    ),
    "zhaoliu": User(
        user_id="zhaoliu",
        name="赵六",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("zhaoliu123"),
        dingtalk_user_id=None,
    ),
}


class UserRepository:
    """MVP 用户存储：内存字典，预置 4 个用户，密码 PBKDF2 哈希。"""

    def __init__(self) -> None:
        self._users: dict[str, User] = dict(_BUILTIN_USERS)

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def list_by_role(self, role: str) -> list[User]:
        return [u for u in self._users.values() if u.role == role]

    def list_all(self) -> list[User]:
        return list(self._users.values())

    def employee_ids(self) -> list[str]:
        return [u.user_id for u in self._users.values() if u.role == UserRole.EMPLOYEE]
