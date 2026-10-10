"""Контракт входа графовой модели: порядок, направления, маски и снимки."""

import unittest
import json
from dataclasses import asdict

import numpy as np

from tsim.env import ObservationSpec, TrafficEnv


class GraphEnvTest(unittest.TestCase):
    def test_shared_layout_across_worlds(self):
        worlds = ("cross", "grid2", "district", "irregular")
        spec = ObservationSpec.from_worlds(worlds)
        restored = ObservationSpec(**json.loads(json.dumps(asdict(spec))))
        layouts = []
        for world in worlds:
            env = TrafficEnv(world, obs_spec=restored)
            obs = env.reset()
            graph = env.graph_observation()
            layouts.append(env.obs_layout())
            self.assertEqual(graph["x"].shape, (len(env.agents), len(layouts[0])))
            self.assertEqual(graph["action_mask"].shape, (len(env.agents), spec.max_phases))
            self.assertEqual(graph["lane_attr"].shape, (len(env.agents), spec.max_lanes, 6))
            self.assertEqual(graph["phase_ped_mask"].shape, (len(env.agents), spec.max_phases, spec.max_ped))
            np.testing.assert_array_equal(graph["phase_lane_mask"], graph["phase_movement_mask"].any(axis=-1))
            self.assertTrue(np.all(graph["x"][~graph["feature_mask"]] == 0))
            self.assertTrue(np.all(graph["lane_attr"][~graph["lane_mask"]] == 0))
            for i, jid in enumerate(env.agents):
                np.testing.assert_array_equal(graph["x"][i], obs[jid])
                j = env.net.junctions[jid]
                peds = [name for name, g in j.groups.items() if g.kind == "ped"]
                for p, phase in enumerate(j.phases):
                    for k, group_name in enumerate(peds):
                        self.assertEqual(graph["phase_ped_mask"][i, p, k], group_name in phase["green"])
                    # Включённые движения совпадают с коннекторами зелёных групп.
                    expected = {(link.from_lane, link.movement)
                                for group_name in phase["green"] if j.groups[group_name].kind == "car"
                                for li in j.groups[group_name].links for link in [env.net.links[li]]}
                    actual = {(j.approaches[k], graph["movement_names"][m])
                              for k, m in zip(*np.nonzero(graph["phase_movement_mask"][i, p]))}
                    self.assertEqual(actual, expected)
            env.step({})
        self.assertTrue(all(layout == layouts[0] for layout in layouts))

    def test_too_small_layout_is_rejected(self):
        for spec in (ObservationSpec(1, 10, 10), ObservationSpec(20, 1, 10), ObservationSpec(20, 10, 0)):
            with self.assertRaisesRegex(ValueError, "миру нужно"):
                TrafficEnv("grid2", obs_spec=spec)
        for args in ((0, 1, 0), (1, 0, 0), (1, 1, -1), (1.5, 1, 0)):
            with self.assertRaises(ValueError):
                ObservationSpec(*args)
        with self.assertRaises(ValueError):
            ObservationSpec.from_worlds([])

    def test_road_features_and_direction(self):
        env = TrafficEnv("grid2")
        graph = env.graph()  # статический граф доступен до reset
        nodes = graph["nodes"]
        features = dict(zip(graph["edges"], graph["edge_features"]))
        self.assertEqual(len(features), 8)
        a, b, c = (nodes.index(j) for j in ("j00", "j01", "j10"))
        north, south, east = features[a, b], features[b, a], features[a, c]
        self.assertAlmostEqual(north[0], 1.7)  # расстояние между центрами 170 м
        self.assertGreater(north[1], 0)
        self.assertLess(north[1], north[0])  # полосы обрезаны у перекрёстков
        self.assertAlmostEqual(north[2], north[1] * 10 / 16.7)
        self.assertEqual(north[3], 0.5)  # две сквозные полосы, карман не третья
        self.assertEqual(east[3], 0.25)  # горизонтальная улица однополосная
        np.testing.assert_array_equal(north[4:], [0, 1])
        np.testing.assert_array_equal(south[4:], [0, -1])
        np.testing.assert_array_equal(east[4:], [1, 0])

    def test_single_node_and_empty_edges(self):
        env = TrafficEnv("cross")
        with self.assertRaisesRegex(RuntimeError, "reset"):
            env.graph_observation()
        obs = env.reset()
        graph = env.graph_observation()
        self.assertEqual(graph["edge_index"].shape, (2, 0))
        self.assertEqual(graph["edge_attr"].shape, (0, 6))
        np.testing.assert_array_equal(graph["attention_mask"], [[True]])
        np.testing.assert_array_equal(graph["x"][0], obs[env.agents[0]])
        self.assertEqual(graph["x"].dtype, np.float32)
        self.assertEqual(graph["edge_index"].dtype, np.int64)

    def test_neighbor_attention_and_current_state(self):
        env = TrafficEnv("grid2", decision=10)
        obs = env.reset()
        before = env.graph_observation()
        for i, jid in enumerate(before["nodes"]):
            np.testing.assert_array_equal(before["x"][i], obs[jid])
            np.testing.assert_array_equal(before["action_mask"][i], env.action_mask(jid))
        a = before["nodes"].index("j00")
        b = before["nodes"].index("j11")
        self.assertFalse(before["attention_mask"][a, b])  # диагональный узел не сосед
        self.assertTrue(np.all(np.diag(before["attention_mask"])))
        obs, _, _, _ = env.step({})
        after = env.graph_observation()
        self.assertTrue(np.all(before["action_mask"].sum(axis=1) == 1))
        self.assertTrue(np.all(after["action_mask"].sum(axis=1) > 1))
        for i, jid in enumerate(after["nodes"]):
            np.testing.assert_array_equal(after["x"][i], obs[jid])
        self.assertFalse(np.array_equal(before["x"], after["x"]))
        # Снимки можно хранить в буфере обучения: следующие шаги их не меняют.
        env.reset()
        fresh = env.graph_observation()
        np.testing.assert_array_equal(before["x"], fresh["x"])
        after["edge_attr"][:] = -1
        self.assertTrue(np.all(fresh["edge_attr"][:, :4] > 0))

    def test_padding_on_irregular_network(self):
        env = TrafficEnv("irregular")
        env.reset()
        graph = env.graph_observation()
        self.assertEqual(graph["feature_mask"].shape, graph["x"].shape)
        self.assertTrue(np.any(~graph["feature_mask"]))
        self.assertTrue(np.all(graph["x"][~graph["feature_mask"]] == 0))
        phase_start = env.max_lanes * 4
        for i, jid in enumerate(graph["nodes"]):
            junction = env.net.junctions[jid]
            n_ped = sum(g.kind == "ped" for g in junction.groups.values())
            expected = len(junction.approaches) * 4 + env.n_actions(jid) + 4 + n_ped
            self.assertEqual(int(graph["feature_mask"][i].sum()), expected)
            self.assertFalse(np.any(graph["action_mask"][i, env.n_actions(jid):]))
            self.assertFalse(np.any(graph["feature_mask"][i, phase_start + env.n_actions(jid):
                                                            phase_start + env.max_phases]))


if __name__ == "__main__":
    unittest.main()
