# -*- coding: utf-8 -*-
"""
全局应用上下文 —— 管理当前选中的门店，供所有模块查询时使用
"""
import threading


class AppContext:
    """应用上下文单例，保存当前门店 ID 和名称"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._store_id = None  # None = 全部门店
                    cls._instance._store_name = "全部门店"
                    cls._instance._current_username = None  # 当前登录用户名
        return cls._instance

    @property
    def store_id(self):
        return self._store_id

    @property
    def store_name(self):
        return self._store_name

    def set_store(self, store_id, store_name):
        self._store_id = store_id
        self._store_name = store_name

    @property
    def current_username(self):
        return self._current_username

    def set_current_user(self, username):
        self._current_username = username

    def is_all_stores(self):
        return self._store_id is None

    def get_store_filter(self):
        """返回 (store_id, is_all) 供查询使用"""
        return self._store_id, self.is_all_stores()


def get_app_context():
    return AppContext()
