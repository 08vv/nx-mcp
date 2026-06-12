from unittest.mock import MagicMock

class Part:
    class Units:
        Millimeters = "mm"

class Features:
    class BooleanBuilder:
        class BooleanType:
            Unite = "Unite"
            Subtract = "Subtract"

    class EdgeBlendBuilder:
        class OverflowType:
            ClearEdges = "ClearEdges"

class BasePart:
    pass

class Assemblies:
    class AddComponentBuilder:
        class LocationType:
            AbsoluteCoordinates = "AbsoluteCoordinates"

class _View:
    def Fit(self): print("[MOCK] Fit")
    def Orient(self, n): print(f"[MOCK] Orient {n}")
    def SaveImage(self, p, w, h): print(f"[MOCK] SaveImage {p}")

class _ModelingViews:
    def __init__(self):
        self.WorkView = _View()

class _UI:
    _inst = None
    def __init__(self):
        self.ModelingViews = _ModelingViews()
    @classmethod
    def GetUI(cls):
        if cls._inst is None:
            cls._inst = _UI()
        return cls._inst

UI = _UI

class _DexManager:
    def _exporter(self):
        m = MagicMock()
        m.Commit = MagicMock()
        m.Destroy = MagicMock()
        return m
    def CreateStepCreator(self): return self._exporter()
    def CreateStlCreator(self):  return self._exporter()

class _FeaturesCollection:
    def _builder(self):
        b = MagicMock()
        b.CommitFeature = MagicMock(return_value=MagicMock())
        b.Destroy = MagicMock()
        return b
    def CreateExtrudeBuilder(self, _):      return self._builder()
    def CreateRevolveBuilder(self, _):      return self._builder()
    def CreateBooleanBuilder(self, _):      return self._builder()
    def CreateEdgeBlendBuilder(self, _):    return self._builder()
    def CreateChamferBuilder(self, _):      return self._builder()
    def CreateHoleBuilder(self, _):         return self._builder()
    def CreateMirrorFeatureBuilder(self,_): return self._builder()
    def CreateLinearPatternBuilder(self,_): return self._builder()
    def ToArray(self): return []

class _SketchCollection:
    def CreateSketchInPlaceBuilder2(self, _):
        b = MagicMock()
        b.Commit = MagicMock(return_value=MagicMock())
        b.Destroy = MagicMock()
        return b

class _PartsCollection:
    def __init__(self):
        self._work = _WorkPart()
    def NewDisplay(self, f, u): print(f"[MOCK] NewDisplay {f}"); return MagicMock()
    def Open(self, f):          print(f"[MOCK] Open {f}"); return MagicMock()
    @property
    def Work(self): return self._work

class _WorkPart:
    def __init__(self):
        self.Features = _FeaturesCollection()
        self.Sketches  = _SketchCollection()
        self.Curves    = MagicMock()
        self.AssemblyManager = MagicMock()
        self.ComponentAssembly = MagicMock()
    def Save(self): print("[MOCK] Save")

class _Session:
    _inst = None
    def __init__(self):
        self.Parts           = _PartsCollection()
        self.DexManager      = _DexManager()
        self.MeasureManager  = MagicMock()
        self.AssemblyManager = MagicMock()
    @classmethod
    def GetSession(cls):
        if cls._inst is None:
            cls._inst = _Session()
        return cls._inst

Session = _Session

class Point3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = x, y, z

class Vector3d:
    def __init__(self, x=0.0, y=0.0, z=1.0):
        self.X, self.Y, self.Z = x, y, z