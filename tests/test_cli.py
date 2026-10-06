import json

import cli


def run(argv, capsys):
    code = cli.main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_read_prints_json_and_exits_0(tmp_path, capsys):
    db = str(tmp_path / "a.db")
    code, out = run(["read", "facebook/react", "--db", db], capsys)
    assert code == 0
    assert out["success"] is True and out["count"] == 0


def test_invalid_repo_exits_1_with_error_json(tmp_path, capsys):
    db = str(tmp_path / "a.db")
    code, out = run(["import", "not-a-repo", "--db", db], capsys)
    assert code == 1
    assert out["error"]["code"] == "INVALID_REPO"


def test_db_path_precedence_flag_then_env_then_default(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RR_DB_PATH", raising=False)
    run(["read", "a/b"], capsys)
    assert (tmp_path / "issues.db").exists()  # default

    monkeypatch.setenv("RR_DB_PATH", str(tmp_path / "env.db"))
    run(["read", "a/b"], capsys)
    assert (tmp_path / "env.db").exists()  # env var

    run(["read", "a/b", "--db", str(tmp_path / "flag.db")], capsys)
    assert (tmp_path / "flag.db").exists()  # flag wins
