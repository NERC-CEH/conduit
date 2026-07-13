"""Tests for conduit.formats — the single file-format registry."""

import pytest

from conduit.formats import (
    FORMATS,
    format_for,
    group_suffixes,
    supported_suffixes,
)


class TestFormatFor:
    @pytest.mark.parametrize(
        ("path", "key"),
        [
            ("a.nc", "netcdf"),
            ("a.netcdf", "netcdf"),
            ("a.zarr", "zarr"),
            ("a.csv", "csv"),
            ("a.parquet", "parquet"),
            ("a.pq", "parquet"),
            ("a.json", "json"),
            ("a.toml", "toml"),
        ],
    )
    def test_dispatches_by_extension(self, path, key):
        assert format_for(path).key == key

    def test_extension_matching_is_case_insensitive(self):
        assert format_for("A.NC").key == "netcdf"

    def test_suffixless_directory_reads_as_zarr(self, tmp_path):
        store = tmp_path / "store"
        store.mkdir()
        assert format_for(store).key == "zarr"

    def test_unknown_extension_error_lists_all_formats(self):
        with pytest.raises(ValueError, match="Unsupported file extension") as exc:
            format_for("foo.txt")
        message = str(exc.value)
        # Every supported extension is named — not just those of whichever loader
        # happened to be last in an if-chain (the old CSV-only message).
        for suffix in supported_suffixes():
            assert suffix in message

    def test_writable_lookup_rejects_input_only_formats(self):
        # JSON/TOML are readable but have no writer.
        with pytest.raises(ValueError, match="input-only"):
            format_for("out.json", writable=True)

    def test_writable_lookup_allows_writable_formats(self):
        assert format_for("out.csv", writable=True).key == "csv"


class TestRegistryShape:
    def test_every_format_is_readable(self):
        assert all(fmt.read is not None for fmt in FORMATS)

    def test_suffixes_are_unique_across_formats(self):
        seen = [s for fmt in FORMATS for s in fmt.suffixes]
        assert len(seen) == len(set(seen))

    def test_suffixes_are_lowercase_and_dotted(self):
        for fmt in FORMATS:
            for suffix in fmt.suffixes:
                assert suffix.startswith(".")
                assert suffix == suffix.lower()

    def test_only_table_formats_write_frames(self):
        for fmt in FORMATS:
            assert (fmt.write_frame is not None) == (fmt.group == "table")

    def test_subset_capable_formats_are_the_dataset_ones(self):
        # [subset] partial writes need NetCDF (a file per part) or Zarr (regions).
        assert {f.key for f in FORMATS if f.supports_subset} == {"netcdf", "zarr"}

    def test_only_zarr_needs_a_prepared_store(self):
        assert {f.key for f in FORMATS if f.needs_store} == {"zarr"}

    def test_groups_partition_the_registry(self):
        assert group_suffixes("dataset") == [".nc", ".netcdf", ".zarr"]
        assert group_suffixes("table") == [".csv", ".parquet", ".pq"]
        assert group_suffixes("scalar") == [".json", ".toml"]

    def test_supported_suffixes_writable_excludes_input_only(self):
        writable = supported_suffixes(writable=True)
        assert ".json" not in writable
        assert ".toml" not in writable
        assert ".nc" in writable
