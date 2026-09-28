from textkit.case import camel_to_snake, snake_to_camel


def test_camel_to_snake():
    assert camel_to_snake("helloWorld") == "hello_world"
    assert camel_to_snake("HTTPServerError") == "http_server_error"
    assert camel_to_snake("getX") == "get_x"
    assert camel_to_snake("already_snake") == "already_snake"
    assert camel_to_snake("Version2Update") == "version2_update"
    assert camel_to_snake("") == ""
    assert camel_to_snake("parseJSONData") == "parse_json_data"


def test_snake_to_camel():
    assert snake_to_camel("http_server_error") == "httpServerError"
    assert snake_to_camel("http_server_error", upper=True) == "HttpServerError"
    assert snake_to_camel("__a__b_") == "aB"
    assert snake_to_camel("") == ""
    assert snake_to_camel("single") == "single"
