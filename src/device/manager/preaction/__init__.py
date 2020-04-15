import abc


class Action(object):

    @abc.abstractmethod
    def execute(self, config, device_types, on_finish):
        pass

    @classmethod
    def build_settings(cls):
        return None

    @classmethod
    def build_config(cls, config):
        pass

    @abc.abstractmethod
    def undo(self, on_finish):
        pass
