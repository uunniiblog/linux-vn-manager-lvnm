from abc import ABC, abstractmethod

class DesktopUtilsInterface(ABC):
    @abstractmethod
    def get_all_window_ids(self): pass

    @abstractmethod
    def get_window_name(self, wid): pass

    @abstractmethod
    def get_window_pid(self, wid): pass

    @abstractmethod
    def get_active_window_id(self): pass

    @abstractmethod
    def find_window_id_by_title(self, target_title): pass

    @abstractmethod
    def find_window_by_pid(self, target_pid): pass

