from .nxopen_loader import load_nxopen

class NXSession:
    _instance = None
    _nxopen = None

    @classmethod
    def reset(cls):
        cls._instance = None
        cls._nxopen = None

    @classmethod
    def nxopen(cls):
        if cls._nxopen is None:
            cls._nxopen = load_nxopen()
        return cls._nxopen

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls.nxopen().Session.GetSession()
        return cls._instance

    @classmethod
    def work_part(cls):
        return cls.get().Parts.Work

    @classmethod
    def ui(cls):
        return cls.nxopen().UI.GetUI()
