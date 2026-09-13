"""T15 Phase 0 student-study scenes for trusted, fixed templates only.

These scenes accept no external input and intentionally avoid Tex/MathTex so the
minimal renderer image does not require a TeX distribution.
"""

import math

from manim import (
    Axes,
    BLUE,
    Create,
    DOWN,
    FadeIn,
    FadeOut,
    GREEN,
    LEFT,
    RED,
    ReplacementTransform,
    RIGHT,
    Scene,
    Text,
    UP,
    WHITE,
    YELLOW,
)


class RiemannSumApproximation(Scene):
    """Show left rectangles converging toward the area under y=x^2 on [0, 2]."""

    def construct(self) -> None:
        axes = Axes(
            x_range=[-0.2, 2.4, 0.5],
            y_range=[-0.5, 4.5, 1],
            x_length=7,
            y_length=4.8,
            axis_config={"color": WHITE, "include_tip": False},
        ).shift(LEFT * 0.5 + DOWN * 0.3)
        graph = axes.plot(lambda x: x * x, x_range=[0, 2], color=BLUE)
        title = Text("Riemann sums approach area", font_size=34).to_edge(UP)
        exact = Text("exact area under y = x^2 on [0, 2]: 2.667", font_size=22)
        exact.to_corner(DOWN + LEFT)

        self.play(Create(axes), Create(graph), FadeIn(title), FadeIn(exact))

        previous_rectangles = None
        previous_label = None
        for count in (4, 8, 16):
            rectangles = axes.get_riemann_rectangles(
                graph,
                x_range=[0, 2],
                dx=2 / count,
                input_sample_type="left",
                color=(GREEN, YELLOW),
                fill_opacity=0.65,
                stroke_width=1,
            )
            approximate_area = sum((2 * index / count) ** 2 for index in range(count)) * (2 / count)
            label = Text(
                f"rectangles: {count}    estimate: {approximate_area:.3f}",
                font_size=24,
                color=GREEN,
            ).to_corner(DOWN + RIGHT)
            if previous_rectangles is None:
                self.play(FadeIn(rectangles), FadeIn(label))
            else:
                self.play(
                    ReplacementTransform(previous_rectangles, rectangles),
                    ReplacementTransform(previous_label, label),
                    run_time=1.5,
                )
            previous_rectangles = rectangles
            previous_label = label
            self.wait(0.5)

        self.wait(0.5)


class TaylorApproximation(Scene):
    """Show successive odd Taylor polynomials approximating sin(x)."""

    def construct(self) -> None:
        axes = Axes(
            x_range=[-math.pi, math.pi, math.pi / 2],
            y_range=[-2, 2, 0.5],
            x_length=9,
            y_length=4.8,
            axis_config={"color": WHITE, "include_tip": False},
        ).shift(DOWN * 0.25)
        sine = axes.plot(math.sin, x_range=[-math.pi, math.pi], color=BLUE)
        title = Text("Taylor polynomials approach sin(x)", font_size=34).to_edge(UP)
        target_label = Text("blue: sin(x)", font_size=22, color=BLUE).to_corner(DOWN + LEFT)

        approximations = (
            ("degree 1: x", lambda x: x),
            ("degree 3: x - x^3 / 6", lambda x: x - x**3 / 6),
            ("degree 5: add x^5 / 120", lambda x: x - x**3 / 6 + x**5 / 120),
        )

        self.play(Create(axes), Create(sine), FadeIn(title), FadeIn(target_label))
        previous_curve = None
        previous_label = None
        for label_text, function in approximations:
            curve = axes.plot(function, x_range=[-math.pi, math.pi], color=RED)
            label = Text(label_text, font_size=24, color=RED).to_corner(DOWN + RIGHT)
            if previous_curve is None:
                self.play(Create(curve), FadeIn(label), run_time=1.5)
            else:
                self.play(FadeOut(previous_label), run_time=0.2)
                self.play(
                    ReplacementTransform(previous_curve, curve),
                    FadeIn(label),
                    run_time=1.3,
                )
            previous_curve = curve
            previous_label = label
            self.wait(0.5)

        self.wait(0.5)
