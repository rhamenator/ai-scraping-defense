
# Re-export util modules from the project source so test imports like
# ``from util import robots_fetcher`` resolve correctly when the ``test``
# package shadows the real package on ``sys.path``.
from src.util import corpus_wikipedia_updater, robots_fetcher

__all__ = ['corpus_wikipedia_updater', 'robots_fetcher']
