from typing import Tuple


class ParetoCalculator:
    """
    Truncated Pareto distribution calculator.

    Parameters
    ----------
    min_layer: float
        The minimum layer and value of the truncated Pareto distribution. Typically 1.
    max_layer: float
        The maximum layer but value + 1 of the truncated Pareto distribution. 1 is added
        because probability of the maximum x layer is CDF(x+1) - CDF(x), which means that
        the CDF must spans from minimum layer to maximum layer + 1.
    """

    def __init__(self, min_layer: float, max_layer: float):
        self.min_layer = min_layer
        self.max_layer = max_layer + 1

    def pdf(self, x: float, alpha: float) -> float:
        """
        The probability density function of the truncated Pareto distribution.

        Parameters
        ----------
        x : float
            The 'layer' value. May not necessarily be an integer.
        alpha : float
            The Pareto index.

        Returns
        -------
        float
            The value of the probability density function at `x`.
        """
        if x <= self.min_x or x > self.max_x:
            return 0.0

        C = self.min_x ** (-alpha) - self.max_x ** (-alpha)
        result = (alpha / C) * x ** (-alpha - 1)
        return result

    def inverse_pdf(self, y: float, alpha: float) -> float:
        """
        The inverse of the probability density function of the truncated Pareto
        distribution.

        Parameters
        ----------
        y : float
            The value of the probability density function.
        alpha : float
            The Pareto index.

        Returns
        -------
        float
            The 'layer' number that corresponds to the value of the probability density
            function `y`.
        """
        if y <= 0.0:
            return self.max_x

        C = self.min_x ** (-alpha) - self.max_x ** (-alpha)
        return (alpha / (C * y)) ** (-alpha - 1)

    def cdf(self, x: float, alpha: float) -> float:
        """
        The cumulative distribution function of the truncated Pareto distribution.

        Parameters
        ----------
        x : float
            The 'layer' value. May not necessarily be an integer.
        alpha : float
            The Pareto index.

        Returns
        -------
        float
            The value of the cumulative distribution function at `x`.
        """
        if x <= self.min_x:
            return 0.0
        elif x > self.max_x:
            return 1.0

        C = 1 - (self.min_x / self.max_x) ** alpha
        result = 1 - (self.min_x**alpha / C) * (x**-alpha - self.max_x**-alpha)

        return result

    def inverse_cdf(self, y: float, alpha: float) -> float:
        """
        The inverse of the cumulative distribution function of the truncated Pareto
        distribution.

        Parameters
        ----------
        y : float
            The value of the cumulative distribution function.
        alpha : float
            The Pareto index.

        Returns
        -------
        float
            The 'layer' number that corresponds to the value of the cumulative
            distribution function `y`.
        """
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
        """
        Iterative method to find the Pareto index that satisfies the given p and q. In 
        Pareto distribution, p of the consequences come from q of the causes.

        Parameters
        ----------
        p : float
            The proportion of the consequences in decimal.
        q : float
            The proportion of the causes in decimal.
        tolerance : float, optional
            The tolerance for the iterative method, by default 1e-5.
        alpha_search_range : Tuple[float, float], optional
            The range of the Pareto index to search for, by default (0.01, 5).

        Returns
        -------
        Tuple[float, float]
            The cut-off point (x0) and Pareto index (alpha) that satisfies the given p
            and q.
        """
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
        """
        Calculate the probability of a given layer.

        Parameters
        ----------
        layer : int
            The layer number.
        alpha : float
            The Pareto index.

        Returns
        -------
        float
            The probability of the given layer.
        """
        return self.cdf(layer + 1, alpha) - self.cdf(layer, alpha)

    def theoretical_cdf_minimum(self, x: float) -> float:
        """
        The theoretical minimum of the cumulative distribution function of the truncated
        Pareto distribution, which is given by having Pareto index close to 0.

        Parameters
        ----------
        x : float
            The layer value. May not necessarily be an integer.

        Returns
        -------
        float
            The value of the cumulative distribution function at `x`.
        """
        return self.cdf(x, alpha=0.001)
