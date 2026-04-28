from noteration.config import NoterationConfig

def test_config_defaults(temp_vault):
    config = NoterationConfig(temp_vault)
    assert config.theme == "system"
    assert config.font_size == 12
    assert config.papis_library == temp_vault / "literature"

def test_config_save_load(temp_vault):
    config = NoterationConfig(temp_vault)
    config.set("ui", "theme", "dark")
    config.set("editor", "font_size", 16)
    config.save()
    
    # Reload
    new_config = NoterationConfig(temp_vault)
    assert new_config.theme == "dark"
    assert new_config.font_size == 16
