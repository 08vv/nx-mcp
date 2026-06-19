import sys
from pathlib import Path

import NXOpen
import NXOpen.UF


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("cylinder_r10_h50_chamfer5_bottom_blend2.prt").resolve()


def _make_cylinder(work_part, radius, height):
    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        direction = NXOpen.Vector3d(0.0, 0.0, 1.0)
        nx_direction = work_part.Directions.CreateDirection(
            origin,
            direction,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Diameter.RightHandSide = str(radius * 2.0)
        builder.Height.RightHandSide = str(height)
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_direction
        return builder.Commit()
    finally:
        builder.Destroy()


def _add_chamfer(work_part, body, offset):
    edges = list(body.GetEdges())
    if not edges:
        raise RuntimeError("Created cylinder has no edges to chamfer")

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = str(offset)
        builder.SecondOffset = str(offset)
        builder.Angle = "45"
        builder.Tolerance = 0.01

        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge,
                NXOpen.Edge.Null,
                False,
                0.5,
                False,
            )
            for edge in edges
        ]
        collector = work_part.ScCollectors.CreateCollector()
        collector.ReplaceRules(rules, False)
        builder.SmartCollector = collector
        return builder.CommitFeature()
    finally:
        builder.Destroy()


def _edge_z_range(uf_session, edge):
    pt1, pt2, _vertex_count = uf_session.Modeling.AskEdgeVerts(edge.Tag)
    return min(pt1[2], pt2[2]), max(pt1[2], pt2[2])


def _bottom_edges(uf_session, body):
    edges = list(body.GetEdges())
    ranges = [(edge, *_edge_z_range(uf_session, edge)) for edge in edges]
    min_z = min(edge_min for _edge, edge_min, _edge_max in ranges)
    return [
        edge
        for edge, edge_min, edge_max in ranges
        if abs(edge_min - min_z) < 0.001 and abs(edge_max - min_z) < 0.001
    ]


def _add_edge_blend(work_part, uf_session, body, radius):
    edges = _bottom_edges(uf_session, body)
    if not edges:
        raise RuntimeError("Could not find bottom edge for edge blend")

    builder = work_part.Features.CreateEdgeBlendBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(
            edges,
            0.5,
            True,
        )
        collector.ReplaceRules([rule], False)

        builder.Tolerance = 0.01
        builder.AllInstancesOption = False
        builder.RemoveSelfIntersection = True
        builder.ConvexConcaveY = False
        builder.RollOverSmoothEdge = True
        builder.RollOntoEdge = True
        builder.MoveSharpEdge = True
        builder.OverlapOption = NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        builder.BlendOrder = NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        builder.SetbackOption = NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        builder.AddChainset(collector, str(radius))
        builder.CommitFeature()
    finally:
        builder.Destroy()


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    feature = _make_cylinder(work_part, radius=10.0, height=50.0)
    body = feature.GetBodies()[0]
    chamfer = _add_chamfer(work_part, body, offset=5.0)
    chamfered_body = chamfer.GetBodies()[0]
    _add_edge_blend(work_part, uf_session, chamfered_body, radius=2.0)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created chamfered cylinder with bottom blend: {output_path}")


if __name__ == "__main__":
    main()
