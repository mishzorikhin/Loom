import copy
import unittest

from tsim.compiler import CompileError, compile_world, load_world, net_json
from tsim.generators import corridor, district, grid, irregular
from tsim.worlds import ROOT

CROSS = load_world(ROOT / "examples" / "cross.json")


class CompilerTest(unittest.TestCase):
    def test_cross_compiles(self):
        net = compile_world(CROSS)
        lanes = [l for l in net.links if l.kind == "lane"]
        conns = [l for l in net.links if l.kind == "conn"]
        self.assertEqual(len(lanes), 14)
        self.assertEqual(len(conns), 14)
        # 4 перехода на перекрёстке и 1 посреди квартала
        self.assertEqual(len(net.crosswalks), 5)
        self.assertIn("mb_school", net.junctions)

    def test_arrows_make_connectors(self):
        net = compile_world(CROSS)
        pocket = net.link("rn.backward.2")
        self.assertEqual(pocket.pocket, 60)
        moves = {net.links[c].movement for c in pocket.next}
        self.assertEqual(moves, {"left"})
        curb = net.link("rn.backward.0")
        self.assertEqual({net.links[c].movement for c in curb.next}, {"straight", "right"})
        # левый поворот с севера уходит на восток в левую полосу выезда
        left = net.links[pocket.next[0]]
        self.assertEqual(net.links[left.to_lane].road, "re")

    def test_yield_only_for_permissive_peds(self):
        net = compile_world(CROSS)
        right = next(l for l in net.links if l.kind == "conn" and l.id.startswith("a:rn.backward.0>rw"))
        rules = {(c.kind, c.rule) for c in right.conflicts if c.kind == "ped"}
        self.assertIn(("ped", "yield"), rules)
        left = next(l for l in net.links if l.kind == "conn" and l.movement == "left" and l.id.startswith("a:rn"))
        self.assertTrue(all(c.rule == "protected" for c in left.conflicts if c.kind == "ped"))

    def test_unsafe_phase_rejected(self):
        w = copy.deepcopy(CROSS)
        w["junctions"]["a"]["signal"]["phases"][0]["green"].append("ns_left")
        with self.assertRaises(CompileError) as e:
            compile_world(w)
        self.assertTrue(any("пересекаются в одной фазе" in m for m in e.exception.errors))

    def test_arrow_without_exit_rejected(self):
        w = copy.deepcopy(CROSS)
        del w["roads"]["rw"]
        del w["nodes"]["w"]
        with self.assertRaises(CompileError):
            compile_world(w)

    def test_schema_errors_have_paths(self):
        w = copy.deepcopy(CROSS)
        w["roads"]["rn"]["forward"][0]["width"] = 9
        with self.assertRaises(CompileError) as e:
            compile_world(w)
        self.assertTrue(any(m.startswith("roads/rn/forward/0/width") for m in e.exception.errors))

    def test_generators_and_auto_signals(self):
        for w in (grid(3, 3), grid(2, 2), corridor(4), district(), irregular()):
            net = compile_world(w)
            for j in net.junctions.values():
                self.assertGreaterEqual(len(j.phases), 2)
                # каждое движение в какой-то группе
                for ci in j.links:
                    self.assertTrue(net.links[ci].group)

    def test_net_json_roundtrip(self):
        js = net_json(compile_world(CROSS))
        self.assertEqual(len(js["links"]), 28)
        self.assertTrue(js["render"]["arrows"])
        self.assertTrue(js["render"]["heads"])
        self.assertEqual(len(js["render"]["zebras"]), 5)


if __name__ == "__main__":
    unittest.main()
