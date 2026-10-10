"""Контракт входа графовой модели: порядок, направления, маски и снимки."""

import unittest

import numpy as np

from tsim.env import TrafficEnv


class GraphEnvTest(unittest.TestCase):
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
        env = TrafficEnv("perm")
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
