"""T15 Phase 0：固定可信的割线趋近切线 Manim 场景。

本文件只用于验证独立 renderer 镜像、资源限制和视频产物，不接受用户输入，
也不代表后续允许执行 LLM 生成的 Python 代码。
"""

from manim import (
    Axes,
    BLUE,
    Create,
    Dot,
    DOWN,
    FadeIn,
    GREEN,
    LEFT,
    Line,
    RED,
    RIGHT,
    Scene,
    Text,
    UP,
    ValueTracker,
    VGroup,
    WHITE,
    always_redraw,
    linear,
)


class SecantToTangent(Scene):
    """展示 y=x² 在 x=1 处的割线斜率趋近切线斜率 2。"""

    def construct(self) -> None:
        axes = Axes(
            x_range=[-0.5, 3.2, 0.5],
            y_range=[-0.5, 8.5, 1],
            x_length=7,
            y_length=5,
            axis_config={"color": WHITE, "include_tip": False},
        ).shift(LEFT * 0.4 + DOWN * 0.25)
        graph = axes.plot(lambda x: x * x, x_range=[-0.25, 2.9], color=BLUE)

        fixed_x = 1.0
        moving_x = ValueTracker(2.6)
        fixed_dot = Dot(axes.c2p(fixed_x, fixed_x * fixed_x), color=RED)
        moving_dot = always_redraw(
            lambda: Dot(
                axes.c2p(moving_x.get_value(), moving_x.get_value() ** 2),
                color=GREEN,
            )
        )

        secant = always_redraw(
            lambda: self._secant_line(axes, fixed_x, moving_x.get_value())
        )
        # 使用 Pango Text 而非 DecimalNumber/MathTex，验证 MVP 可以不依赖 LaTeX。
        slope_value = always_redraw(
            lambda: Text(
                f"{fixed_x + moving_x.get_value():.3f}",
                font_size=28,
                color=GREEN,
            ).next_to(axes, RIGHT).shift(UP * 0.2)
        )
        slope_label = Text("secant slope", font_size=24).next_to(slope_value, UP)
        limit_label = Text("limit = tangent slope = 2", font_size=24, color=RED)
        limit_label.next_to(slope_value, DOWN)

        title = Text("Secant approaches tangent for y = x^2", font_size=32)
        title.to_edge(UP)
        legend = VGroup(
            Text("red: fixed point x=1", font_size=20, color=RED),
            Text("green: moving point", font_size=20, color=GREEN),
        ).arrange(DOWN, aligned_edge=LEFT).to_corner(DOWN + RIGHT)

        self.play(Create(axes), Create(graph), FadeIn(title))
        self.play(FadeIn(fixed_dot), FadeIn(moving_dot), Create(secant))
        self.play(FadeIn(slope_label), FadeIn(slope_value), FadeIn(limit_label), FadeIn(legend))
        self.play(moving_x.animate.set_value(1.05), run_time=4.0, rate_func=linear)
        self.wait(0.5)

    @staticmethod
    def _secant_line(axes: Axes, x0: float, x1: float) -> Line:
        slope = x0 + x1
        center_x = (x0 + x1) / 2
        center_y = center_x * center_x
        dx = 1.6
        start = axes.c2p(center_x - dx, center_y - slope * dx)
        end = axes.c2p(center_x + dx, center_y + slope * dx)
        return Line(start, end, color=GREEN)
