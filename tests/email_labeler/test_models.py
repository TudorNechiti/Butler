from agents.email_labeler.models import Category, Classification


def test_schema_offers_exactly_the_five_categories() -> None:
    schema = Classification.model_json_schema()
    enum = schema["$defs"]["Category"]["enum"]
    assert enum == ["debts", "payments", "reminders", "jobs", "other"]
    assert [c.value for c in Category] == enum


def test_schema_has_no_constraints_that_would_fail_client_side() -> None:
    # The API ignores min/max constraints and the SDK would validate them afterwards,
    # failing the whole email. Limits are enforced by the classifier instead.
    properties = Classification.model_json_schema()["properties"]
    for field in properties.values():
        assert not {"minimum", "maximum", "maxLength", "minLength"} & field.keys()
