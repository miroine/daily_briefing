"""Check the shared chart layout without starting Streamlit or fetching data."""
import ast
import unittest
from pathlib import Path

import plotly.graph_objects as go

from core import config


class TestChartLayout(unittest.TestCase):
    def test_legends_are_below_plot_with_expandable_margins(self):
        source = Path(__file__).resolve().parent.parent / "app.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        helper = next(node for node in tree.body
                      if isinstance(node, ast.FunctionDef) and node.name == "style_fig")
        module = ast.Module(body=[helper], type_ignores=[])
        for theme in config.PALETTES:
            for names in (["Brent", "WTI"], list(config.PEERS), list(config.SECTIONS)):
                with self.subTest(theme=theme, names=names):
                    namespace = {"P": config.PALETTES[theme]}
                    exec(compile(module, str(source), "exec"), namespace)
                    fig = go.Figure([
                        go.Scatter(x=[1, 2], y=[1, 2], name=name) for name in names
                    ])
                    styled = namespace["style_fig"](fig, 340, "Chart title")
                    self.assertIs(styled, fig)
                    self.assertEqual(fig.layout.legend.orientation, "h")
                    self.assertEqual(fig.layout.legend.yref, "container")
                    self.assertEqual(fig.layout.legend.y, 0)
                    self.assertEqual(fig.layout.legend.yanchor, "bottom")
                    self.assertTrue(fig.layout.xaxis.automargin)
                    self.assertTrue(fig.layout.margin.autoexpand)
                    self.assertGreaterEqual(fig.layout.margin.b, 80)
                    self.assertGreater(fig.layout.height, 340)
                    self.assertEqual(len(fig.data), len(names))
