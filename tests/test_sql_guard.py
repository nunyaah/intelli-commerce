from reliability.guardrails.sql_guard import validate_sql


def test_allows_plain_select():
    assert validate_sql("SELECT product_name, SUM(total) FROM orders GROUP BY product_name").ok


def test_allows_cte_and_union():
    assert validate_sql(
        "WITH x AS (SELECT total FROM orders) SELECT SUM(total) FROM x"
    ).ok
    assert validate_sql("SELECT id FROM orders UNION SELECT id FROM tickets").ok


def test_blocks_stacked_query_injection():
    v = validate_sql("SELECT * FROM orders; DROP TABLE orders;")
    assert not v.ok
    assert "multiple" in v.reason.lower()


def test_blocks_ddl_and_dml():
    assert not validate_sql("DROP TABLE orders").ok
    assert not validate_sql("DELETE FROM orders WHERE 1=1").ok
    assert not validate_sql("UPDATE orders SET total = 0").ok
    assert not validate_sql("INSERT INTO orders (id) VALUES ('x')").ok


def test_blocks_pragma_and_attach():
    assert not validate_sql("PRAGMA table_info(orders)").ok
    assert not validate_sql("ATTACH DATABASE 'evil.db' AS evil").ok


def test_blocks_schema_escape():
    assert not validate_sql("SELECT * FROM sqlite_master").ok
    assert not validate_sql("SELECT * FROM secret_table").ok


def test_blocks_empty_and_garbage():
    assert not validate_sql("").ok
    assert not validate_sql("not sql at all ;;;").ok
