from digitalafarin_agent.systemd import parse_systemctl_list_units


def test_parser_handles_descriptions_with_spaces():
    sample = """nginx.service loaded active running A high performance web server
my-app.service loaded inactive dead My App Service
"""
    units = parse_systemctl_list_units(sample)
    assert len(units) == 2
    assert units[0].unit_name == "nginx.service"
    assert units[0].description == "A high performance web server"
    assert units[1].sub_state == "dead"
