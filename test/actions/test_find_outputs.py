import hashlib
import json

import pytest

from blight.actions import FindOutputs
from blight.actions.find_outputs import OutputKind
from blight.tool import CC, INSTALL


def test_find_outputs(tmp_path):
    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    cc = CC(["-o", "foo", "foo.c"])
    find_outputs.before_run(cc)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Executable.value,
            "prenormalized_path": "foo",
            "path": str(cc.cwd / "foo"),
            "store_path": None,
            "content_hash": None,
        }
    ]


def test_find_outputs_journaling(monkeypatch, tmp_path):
    journal_output = tmp_path / "journal.jsonl"
    monkeypatch.setenv("BLIGHT_JOURNAL_PATH", str(journal_output))

    store = tmp_path / "store"
    contents = b"not a real object file"
    contents_digest = hashlib.sha256(contents).hexdigest()
    dummy_foo_o = tmp_path / "foo.o"
    dummy_foo_o_store = store / f"{dummy_foo_o.name}-{contents_digest}"

    find_outputs = FindOutputs({"store": store})
    cc = CC(["-c", "foo.c", "-o", str(dummy_foo_o)])
    find_outputs.before_run(cc)
    # Pretend to be the compiler: write some junk to dummy_foo_o
    dummy_foo_o.write_bytes(contents)

    find_outputs.after_run(cc)

    outputs = find_outputs._result["outputs"]
    assert len(outputs) == 1
    assert outputs[0] == {
        "kind": OutputKind.Object.value,
        "prenormalized_path": str(dummy_foo_o),
        "path": dummy_foo_o,
        "store_path": dummy_foo_o_store,
        "content_hash": contents_digest,
    }
    assert dummy_foo_o_store.read_bytes() == contents


def test_find_outputs_multiple(tmp_path):
    fake_cs = [tmp_path / fake_c for fake_c in ["foo.c", "bar.c", "baz.c"]]
    [fake_c.touch() for fake_c in fake_cs]

    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    cc = CC(["-c", *[str(fake_c) for fake_c in fake_cs]])
    find_outputs.before_run(cc)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Object.value,
            "prenormalized_path": fake_c.with_suffix(".o").name,
            "path": str(cc.cwd / fake_c.with_suffix(".o").name),
            "store_path": None,
            "content_hash": None,
        }
        for fake_c in fake_cs
    ]


def test_find_outputs_handles_a_out(tmp_path):
    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    cc = CC(["foo.c"])
    find_outputs.before_run(cc)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Executable.value,
            "prenormalized_path": "a.out",
            "path": str(cc.cwd / "a.out"),
            "store_path": None,
            "content_hash": None,
        }
    ]


def test_find_outputs_store(tmp_path):
    output = tmp_path / "outputs.jsonl"
    store = tmp_path / "store"
    contents = b"not a real object file"
    contents_digest = hashlib.sha256(contents).hexdigest()
    dummy_foo_o = tmp_path / "foo.o"
    dummy_foo_o_store = store / f"{dummy_foo_o.name}-{contents_digest}"

    find_outputs = FindOutputs({"output": output, "store": store})
    cc = CC(["-c", "foo.c", "-o", str(dummy_foo_o)])
    find_outputs.before_run(cc)
    # Pretend to be the compiler: write some junk to dummy_foo_o
    dummy_foo_o.write_bytes(contents)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Object.value,
            "prenormalized_path": str(dummy_foo_o),
            "path": str(dummy_foo_o),
            "store_path": str(dummy_foo_o_store),
            "content_hash": contents_digest,
        }
    ]
    assert dummy_foo_o_store.read_bytes() == contents


def test_find_outputs_store_no_hash(tmp_path):
    output = tmp_path / "outputs.jsonl"
    store = tmp_path / "store"
    contents = b"not a real object file"
    contents_digest = hashlib.sha256(contents).hexdigest()
    dummy_foo_o = tmp_path / "foo.o"
    # Store filename should not have its hash appended
    dummy_foo_o_store = store / dummy_foo_o.name

    find_outputs = FindOutputs({"output": output, "store": store, "append_hash": "false"})
    cc = CC(["-c", "foo.c", "-o", str(dummy_foo_o)])
    find_outputs.before_run(cc)
    # Pretend to be the compiler: write some junk to dummy_foo_o
    dummy_foo_o.write_bytes(contents)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Object.value,
            "prenormalized_path": str(dummy_foo_o),
            "path": str(dummy_foo_o),
            "store_path": str(dummy_foo_o_store),
            "content_hash": contents_digest,
        }
    ]
    assert dummy_foo_o_store.read_bytes() == contents


def test_find_outputs_store_output_does_not_exist(tmp_path):
    output = tmp_path / "outputs.jsonl"
    store = tmp_path / "store"
    dummy_foo_o = tmp_path / "foo.o"

    find_outputs = FindOutputs({"output": output, "store": store})
    cc = CC(["-c", "foo.c", "-o", str(dummy_foo_o)])
    find_outputs.before_run(cc)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Object.value,
            "prenormalized_path": str(dummy_foo_o),
            "path": str(dummy_foo_o),
            "store_path": None,
            "content_hash": None,
        }
    ]


@pytest.mark.parametrize(
    ("soname",),
    [
        ("foo.so",),
        ("foo.so.1",),
        ("foo.so.1.2",),
        ("foo.so.1.2.3",),
    ],
)
def test_find_outputs_annoying_so_prefixes(tmp_path, soname):
    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    cc = CC(["-shared", "-o", soname, "foo.c"])
    find_outputs.before_run(cc)
    find_outputs.after_run(cc)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.SharedLibrary.value,
            "prenormalized_path": soname,
            "path": str(cc.cwd / soname),
            "store_path": None,
            "content_hash": None,
        }
    ]


def test_find_outputs_install(tmp_path):
    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    install = INSTALL(["-c", "foo", "bar", "baz", "/tmp"])
    find_outputs.before_run(install)
    find_outputs.after_run(install)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Executable.value,
            "prenormalized_path": f"/tmp/{name}",
            "path": f"/tmp/{name}",
            "store_path": None,
            "content_hash": None,
        }
        for name in ["foo", "bar", "baz"]
    ]


def test_find_outputs_install_directory_mode(tmp_path):
    output = tmp_path / "outputs.jsonl"

    find_outputs = FindOutputs({"output": output})
    install = INSTALL(["-d", "foo", "bar", "baz"])
    find_outputs.before_run(install)
    find_outputs.after_run(install)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Directory.value,
            "prenormalized_path": name,
            "path": str(install.cwd / name),
            "store_path": None,
            "content_hash": None,
        }
        for name in ["foo", "bar", "baz"]
    ]


def test_find_outputs_install_directory_mode_skip_copy(tmp_path):
    output = tmp_path / "outputs.jsonl"
    dummy = tmp_path / "dummy"
    store = tmp_path / "store"

    find_outputs = FindOutputs({"output": output, "store": store})
    install = INSTALL(["-d", str(dummy)])
    find_outputs.before_run(install)
    # Simulate `install -d`.
    dummy.mkdir()
    find_outputs.after_run(install)

    outputs = json.loads(output.read_text())["outputs"]
    assert outputs == [
        {
            "kind": OutputKind.Directory.value,
            "prenormalized_path": str(dummy),
            "path": str(dummy),
            "store_path": None,
            "content_hash": None,
        }
    ]
