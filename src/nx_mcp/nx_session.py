import NXOpen

class NXSession:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = NXOpen.Session.GetSession()
        return cls._instance

    @classmethod
    def work_part(cls):
        return cls.get().Parts.Work

    @classmethod
    def ui(cls):
        return NXOpen.UI.GetUI()
