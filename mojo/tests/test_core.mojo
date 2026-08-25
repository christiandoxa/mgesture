from std.testing import assert_equal, assert_true, TestSuite


def test_stable_numeric_contract() raises:
    var value: Float32 = 21.0 * 3.0
    assert_equal(value, 63.0)
    assert_true(value > 0.0)


def main() raises:
    TestSuite.discover_tests[__functions_in_module()]().run()
