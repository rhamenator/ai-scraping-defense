# test\tarpit\markov_generator.test.py
import unittest
from tarpit.markov_generator import MarkovGenerator

class TestMarkovGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = MarkovGenerator()

    def test_feed_and_generate(self):
        text = "hello world hello universe hello world again"
        self.generator.feed(text)
        result = self.generator.generate(10)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result.split()), 1)

    def test_generate_without_feed_returns_empty(self):
        result = self.generator.generate(5)
        self.assertEqual(result, "")

    def test_chain_structure(self):
        self.generator.feed("a b c a b d")
        chain = self.generator.chain
        self.assertIn("a", chain)
        self.assertIn("b", chain)
        self.assertIsInstance(chain["a"], list)

    def test_deterministic_output_with_seed(self):
        self.generator.feed("one two three one two four")
        output1 = self.generator.generate(6, seed=42)
        output2 = self.generator.generate(6, seed=42)
        self.assertEqual(output1, output2)

if __name__ == '__main__':
    unittest.main()
