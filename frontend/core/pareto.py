from typing import Tuple


class ParetoCalculator:
    """
    Truncated Pareto distribution calculator.

    Parameters
    ----------
    min_x: float
        The minimum layer and value of the truncated Pareto distribution.
    max_x: float
        The maximum layer but value + 1 of the truncated Pareto distribution. 1 is added
        because probability of the maximum x layer is CDF(x+1) - CDF(x), which means that
        the CDF must spans from minimum x to maximum x + 1.
    """

    def __init__(self, min_x: float, max_x: float):
        self.min_x = min_x
        self.max_x = max_x + 1

    def pdf(self, x: float, alpha: float) -> float:
        if x <= self.min_x or x > self.max_x:
            return 0.0

        C = self.min_x ** (-alpha) - self.max_x ** (-alpha)
        result = (alpha / C) * x ** (-alpha - 1)
        return result

    def inverse_pdf(self, y: float, alpha: float) -> float:
        if y <= 0.0:
            return self.max_x

        C = self.min_x ** (-alpha) - self.max_x ** (-alpha)
        return (alpha / (C * y)) ** (-alpha - 1)

    def cdf(self, x: float, alpha: float) -> float:
        if x <= self.min_x:
            return 0.0
        elif x > self.max_x:
            return 1.0

        C = 1 - (self.min_x / self.max_x) ** alpha
        result = 1 - (self.min_x**alpha / C) * (x**-alpha - self.max_x**-alpha)

        return result

    def inverse_cdf(self, y: float, alpha: float) -> float:
        if y <= 0.0:
            return self.min_x
        elif y >= 1.0:
            return self.max_x

        C = 1 - (self.min_x / self.max_x) ** alpha
        result = ((C * (1 - y) / self.min_x**alpha) + self.max_x**-alpha) ** alpha
        return result

    def get_alpha(
        self,
        p: float,
        q: float,
        tolerance: float = 1e-5,
        alpha_search_range: Tuple[float, float] = (0.01, 5),
    ) -> Tuple[float, float]:
        left, right = alpha_search_range
        x0 = q * (self.max_x - self.min_x) + self.min_x

        while abs(right - left) > tolerance:
            alpha = (left + right) / 2
            cdf_value = self.cdf(x0, alpha)

            if cdf_value < p:
                left = alpha
            else:
                right = alpha

        return x0, (left + right) / 2

    def probability_of_layer(self, layer: int, alpha: float) -> float:
        return self.cdf(layer + 1, alpha) - self.cdf(layer, alpha)

    def theoretical_cdf_minimum(self, x: float) -> float:
        return self.cdf(x, alpha=0.001)
