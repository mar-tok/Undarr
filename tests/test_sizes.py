from core.sizes import format_size


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500 B"

    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_exact_kb_boundary(self):
        assert format_size(1024) == "1.0 KB"

    def test_kb(self):
        assert format_size(2048) == "2.0 KB"

    def test_exact_mb_boundary(self):
        assert format_size(1048576) == "1.0 MB"

    def test_mb(self):
        assert format_size(5 * 1048576) == "5.0 MB"

    def test_exact_gb_boundary(self):
        assert format_size(1073741824) == "1.0 GB"

    def test_gb(self):
        assert format_size(3 * 1073741824) == "3.0 GB"

    def test_exact_tb_boundary(self):
        assert format_size(1099511627776) == "1.0 TB"

    def test_tb(self):
        assert format_size(int(1691.1 * 1073741824)) == "1.7 TB"

    def test_rounding_to_1024_moves_to_next_unit(self):
        assert format_size(int(1023.96 * 1048576)) == "1.0 GB"
