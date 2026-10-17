import json
import os
import threading

import pytest
from fastapi.testclient import TestClient

from stocking import look, presets, server, settings


@pytest.fixture(autouse=True)
def own_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, '_FILE', str(tmp_path / 'settings.json'))


def names():
    return [p['name'] for p in presets.listing()]


def test_a_preset_is_the_cleaned_settings_and_keeps_an_automatic_strength_out():
    presets.save('黑丝', {'style': 'grain', 'density': 120, 'strength': 45, 'strength_auto': True, 'unknown_key': 1})
    (p,) = presets.listing()
    assert p['name'] == '黑丝'
    assert p['params'] == look.clean_params({'style': 'grain', 'density': 120, 'strength_auto': True})
    assert p['params']['strength'] == look.DEFAULTS['strength']
    presets.save('手调', {'strength': 45, 'strength_auto': False})
    assert presets.listing()[1]['params']['strength'] == 45


def test_a_preset_keeps_the_layers_and_their_weights_and_keeps_automatic_strengths_out():
    presets.save('两层', {'style': 'knit', 'weight': 30, 'strength': 45, 'strength_auto': True,
                          'layers': [{'style': 'grain', 'weight': 70, 'strength': 90, 'strength_auto': True},
                                     {'style': 'lines', 'weight': 20, 'strength': 90, 'strength_auto': False}]})
    (p,) = presets.listing()
    first, second, third = look.layer_list(p['params'])
    assert (first['weight'], second['style'], second['weight'], third['style']) == (30, 'grain', 70, 'lines')
    assert (first['strength'], second['strength']) == (look.DEFAULTS['strength'],) * 2 and third['strength'] == 90
    assert presets.snapshot(p['params']) == p['params']
    presets.save('旧', {'style': 'loops'})
    assert presets.listing()[1]['params']['layers'] == []


def test_a_preset_keeps_the_moire_settings_and_one_saved_before_them_reads_as_off():
    presets.save('水波', {'style': 'knit', 'sparkle_on': True, 'moire_on': True, 'moire': 60, 'moire_area': 35,
                          'particle_on': True, 'particle': 75})
    (p,) = presets.listing()
    assert p['params']['sparkle_on'] is True
    assert (p['params']['moire_on'], p['params']['moire'], p['params']['moire_area']) == (True, 60, 35)
    assert (p['params']['particle_on'], p['params']['particle']) == (True, 75)
    settings.update(**{presets.KEY: {'旧': {k: v for k, v in look.DEFAULTS.items()
                                            if k != 'sparkle_on' and not k.startswith(('moire', 'particle'))}}})
    old = presets.listing()[0]['params']
    assert old['sparkle_on'] is False
    assert (old['moire_on'], old['moire'], old['moire_area']) == (False, 100, 100)
    assert (old['particle_on'], old['particle']) == (False, 100)


def test_saving_over_a_name_replaces_it_in_place_and_delete_removes_it():
    presets.save('甲', {'style': 'knit'})
    presets.save('乙', {'style': 'loops'})
    res = presets.save('甲', {'style': 'oily'})
    assert [p['name'] for p in res] == ['甲', '乙'] and res[0]['params']['style'] == 'oily'
    assert names() == ['甲', '乙']
    assert [p['name'] for p in presets.delete('甲')] == ['乙']
    with pytest.raises(ValueError, match='甲'):
        presets.delete('甲')


def test_names_are_trimmed_and_checked_and_settings_are_validated_before_anything_is_stored():
    presets.save('  带空格  ', {})
    assert names() == ['带空格']
    presets.save('x' * presets.MAX_NAME, {})
    for bad in ('', '   ', 'x' * (presets.MAX_NAME + 1), 'a\nb', None):
        with pytest.raises(ValueError):
            presets.save(bad, {})
    for bad in ({'style': 'no-such-style'}, {'density': 'dense'}):
        with pytest.raises(ValueError):
            presets.save('坏', bad)
    assert names() == ['带空格', 'x' * presets.MAX_NAME]


def test_one_unreadable_entry_does_not_break_the_list_and_is_not_rewritten_on_read():
    good = look.clean_params({'style': 'coil'})
    future = dict(good, a_setting_from_a_newer_version=7)
    settings.update(**{presets.KEY: {'好': good, '新版': future, '坏样式': {'style': 'later-style'},
                                     '坏数': {'density': 'x'}, '不是字典': 3}})
    got = {p['name']: p['params'] for p in presets.listing()}
    assert got['好'] == good and got['新版'] == good
    assert got['坏样式'] is None and got['坏数'] is None and got['不是字典'] is None
    assert settings.get(presets.KEY)['新版'] == future                  # listing wrote nothing back
    presets.save('另存', {})
    assert settings.get(presets.KEY)['新版'] == future                  # and neither did a save of another name


def test_a_damaged_store_reads_as_empty():
    settings.update(**{presets.KEY: ['not', 'a', 'dict']})
    assert presets.listing() == []
    presets.save('新的', {})
    assert names() == ['新的']


def test_saves_from_several_threads_all_land_and_other_settings_survive():
    settings.update(lang='en', last_dir='C:/x')
    errors = []

    def work(i):
        try:
            presets.save(f'预设{i}', {'density': 60 + i})
            settings.update(export_dir=f'D:/{i}')
        except Exception as e:                 # pragma: no cover
            errors.append(e)
    threads = [threading.Thread(target=work, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(names()) == sorted(f'预设{i}' for i in range(24))
    assert settings.get('lang') == 'en' and settings.get('last_dir') == 'C:/x'


def test_the_api_lists_saves_overwrites_and_deletes():
    c = TestClient(server.app)
    assert c.get('/api/look/presets').json() == {'presets': []}
    body = {'name': '细腻', 'params': {'style': 'grain', 'density': 110}}
    r = c.put('/api/look/presets', json=body)
    assert r.status_code == 200 and [p['name'] for p in r.json()['presets']] == ['细腻']
    assert c.get('/api/look/presets').json()['presets'][0]['params']['density'] == 110
    body['params']['density'] = 90
    assert c.put('/api/look/presets', json=body).json()['presets'][0]['params']['density'] == 90
    r = c.request('DELETE', '/api/look/presets', json={'name': '细腻'})
    assert r.status_code == 200 and r.json() == {'presets': []}
    assert json.loads(open(settings._FILE, encoding='utf-8').read())[presets.KEY] == {}


def test_the_api_answers_a_bad_request_with_a_message():
    c = TestClient(server.app)
    r = c.put('/api/look/presets', json={'name': ' ', 'params': {}})
    assert r.status_code == 400 and '名字' in r.json()['detail']
    r = c.put('/api/look/presets', json={'name': '甲', 'params': {'style': 'nope'}})
    assert r.status_code == 400
    r = c.request('DELETE', '/api/look/presets', json={'name': '没有这个'})
    assert r.status_code == 400 and '没有这个' in r.json()['detail']
    assert c.get('/api/look/presets').json() == {'presets': []}


def test_the_last_choice_for_auto_100_is_remembered_and_a_new_look_starts_from_it():
    import types
    c = TestClient(server.app)
    new = types.SimpleNamespace(look=None, sparkle=None)
    assert server.blend_auto() is True and server._base_look(new)['lock_total'] is True      # on until turned off
    r = c.put('/api/look/blend-auto', json={'on': False})
    assert r.status_code == 200 and r.json() == {'blend_auto': False}
    assert server.blend_auto() is False and settings.get(server.BLEND_AUTO_KEY) is False
    assert look.clean_params(server._base_look(new))['lock_total'] is False                  # a new look starts off
    painted = types.SimpleNamespace(look=None, sparkle=object())
    assert server._base_look(painted)['lock_total'] is False and server._base_look(painted)['sparkle_painted'] == 100.0
    kept = types.SimpleNamespace(look=look.clean_params({'lock_total': True}), sparkle=None)
    assert server._base_look(kept)['lock_total'] is True                                     # an image keeps its own
    assert c.put('/api/look/blend-auto', json={'on': True}).status_code == 200
    assert server._base_look(new)['lock_total'] is True
    assert c.put('/api/look/blend-auto', json={'on': 'maybe'}).status_code == 422
    settings.update(**{server.BLEND_AUTO_KEY: 'garbage'})
    assert server.blend_auto() is True                                                       # only an explicit off counts


# ---------------------------------------------------------------- preset files

TWO_LAYERS = {'style': 'knit', 'weight': 30, 'strength': 45, 'strength_auto': True, 'sparkle_even': 40,
              'layers': [{'style': 'grain', 'weight': 70, 'amount': 80}], 'lock_total': False}


def write_file(path, data):
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return str(path)


def test_a_preset_file_holds_the_format_the_version_the_name_and_the_settings(tmp_path):
    presets.save('细线加颗粒', TWO_LAYERS)
    data = json.loads(presets.file_text('细线加颗粒'))
    assert (data['format'], data['version'], data['name']) == (presets.FORMAT, presets.VERSION, '细线加颗粒')
    assert data['params'] == presets.listing()[0]['params'] and data['params']['layers'][0]['style'] == 'grain'
    assert data['params']['strength'] == look.DEFAULTS['strength']              # an automatic strength is stored as the default
    assert presets.file_text('细线加颗粒').endswith('\n') and '细线加颗粒' in presets.file_text('细线加颗粒')   # readable, not \u escapes
    with pytest.raises(ValueError, match='没有叫'):
        presets.file_text('没有这个')
    settings.update(**{presets.KEY: {'新版': dict(look.clean_params({}), style='later-style')}})
    with pytest.raises(ValueError, match='读不了'):
        presets.file_text('新版')


def test_the_file_name_is_the_preset_name_made_safe_for_windows():
    assert presets.file_name('黑丝·细线') == '黑丝·细线.json'
    assert presets.file_name('a/b:c*d?e"f<g>h|i\\j') == 'a_b_c_d_e_f_g_h_i_j.json'
    assert presets.file_name('  ..  ') == 'preset.json' and presets.file_name('') == 'preset.json'


def test_an_exported_preset_imports_back_with_everything_it_had(tmp_path):
    presets.save('甲', TWO_LAYERS)
    f = write_file(tmp_path / 'a.json', presets.file_text('甲'))
    presets.delete('甲')
    listing, name, renamed = presets.import_file(f)
    assert (name, renamed) == ('甲', False) and [p['name'] for p in listing] == ['甲']
    assert listing[0]['params'] == presets.snapshot(TWO_LAYERS)                  # layers, amounts and the switch too


def test_an_import_never_replaces_a_preset_a_taken_name_gets_a_number(tmp_path):
    presets.save('甲', {'style': 'loops'})
    f = write_file(tmp_path / 'a.json', {'format': presets.FORMAT, 'version': 1, 'name': '甲', 'params': {'style': 'coil'}})
    _, name, renamed = presets.import_file(f)
    assert (name, renamed) == ('甲 (2)', True)
    _, name, _ = presets.import_file(f)
    assert name == '甲 (3)'
    got = {p['name']: p['params']['style'] for p in presets.listing()}
    assert got == {'甲': 'loops', '甲 (2)': 'coil', '甲 (3)': 'coil'}              # the first one is as it was
    long = 'x' * presets.MAX_NAME
    presets.save(long, {})
    f = write_file(tmp_path / 'b.json', {'format': presets.FORMAT, 'version': 1, 'name': long, 'params': {}})
    _, name, _ = presets.import_file(f)
    assert name == 'x' * (presets.MAX_NAME - 4) + ' (2)' and len(name) == presets.MAX_NAME      # cut to leave room


def test_a_preset_file_without_a_usable_name_takes_its_file_name_and_a_long_name_is_cut(tmp_path):
    ok = {'format': presets.FORMAT, 'version': 1, 'params': {}}
    _, name, _ = presets.import_file(write_file(tmp_path / '朋友的预设.json', ok))
    assert name == '朋友的预设'
    _, name, _ = presets.import_file(write_file(tmp_path / 'c.json', dict(ok, name='a\nb')))
    assert name == 'c'
    _, name, _ = presets.import_file(write_file(tmp_path / 'd.json', dict(ok, name='长' * 60)))
    assert name == '长' * presets.MAX_NAME
    bom = tmp_path / 'e.json'
    bom.write_bytes(b'\xef\xbb\xbf' + json.dumps(dict(ok, name='带BOM')).encode('utf-8'))      # saved by a Windows editor
    assert presets.import_file(str(bom))[1] == '带BOM'


@pytest.mark.parametrize('content, why', [
    ('not json at all', '这不是预设文件'),
    ('[1, 2, 3]', '这不是预设文件'),
    ({'format': 'something-else', 'version': 1, 'params': {}}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'version': 1}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'version': 1, 'params': [1]}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'params': {}}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'version': 'one', 'params': {}}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'version': 0, 'params': {}}, '这不是预设文件'),
    ({'format': presets.FORMAT, 'version': presets.VERSION + 1, 'params': {}}, '新版本'),
    ({'format': presets.FORMAT, 'version': 1, 'params': {'style': 'no-such-style'}}, '未知样式'),
    ({'format': presets.FORMAT, 'version': 1, 'params': {'layers': [{'style': 'nope'}]}}, '未知样式'),
])
def test_a_file_that_is_not_a_good_preset_is_refused_with_a_reason_and_nothing_is_added(tmp_path, content, why):
    f = write_file(tmp_path / 'x.json', content)
    with pytest.raises(ValueError, match=why):
        presets.import_file(f)
    assert presets.listing() == []


def test_a_file_that_is_missing_or_far_too_big_or_not_text_is_refused(tmp_path):
    with pytest.raises(ValueError, match='读不了'):
        presets.import_file(str(tmp_path / 'nope.json'))
    big = write_file(tmp_path / 'big.json', ' ' * (presets.MAX_FILE + 1))
    with pytest.raises(ValueError, match='这不是预设文件'):
        presets.import_file(big)
    binary = tmp_path / 'b.json'
    binary.write_bytes(b'\xff\xfe\x00\x01')
    with pytest.raises(ValueError, match='读不了'):
        presets.import_file(str(binary))
    assert presets.listing() == []


def test_the_api_exports_a_preset_to_the_file_the_dialog_names_and_remembers_the_folder(monkeypatch, tmp_path):
    out = tmp_path / '分享'
    out.mkdir()
    offered = []
    answers = []

    def ask(suggested):
        offered.append(suggested)
        return answers.pop(0)

    monkeypatch.setattr(server, '_ask_preset_save', ask)
    c = TestClient(server.app)
    presets.save('黑丝·细线', TWO_LAYERS)
    answers.append(None)
    assert c.post('/api/look/presets/export', json={'name': '黑丝·细线'}).json() == {'cancelled': True}
    assert offered[-1].endswith('黑丝·细线.json') and not list(out.iterdir())
    answers.append(str(out / '给朋友.json'))
    r = c.post('/api/look/presets/export', json={'name': '黑丝·细线'})
    assert r.status_code == 200 and r.json() == {'file': str(out / '给朋友.json')}
    assert json.loads((out / '给朋友.json').read_text(encoding='utf-8'))['name'] == '黑丝·细线'
    assert [p.name for p in out.iterdir()] == ['给朋友.json']                         # no half-written leftovers
    assert settings.get('preset_dir') == str(out)
    answers.append(None)
    c.post('/api/look/presets/export', json={'name': '黑丝·细线'})
    assert os.path.dirname(offered[-1]) == str(out)                                    # the next dialog opens there
    r = c.post('/api/look/presets/export', json={'name': '没有这个'})
    assert r.status_code == 400 and '没有叫' in r.json()['detail']
    answers.append(str(tmp_path / 'no' / 'such' / 'folder' / 'a.json'))
    r = c.post('/api/look/presets/export', json={'name': '黑丝·细线'})
    assert r.status_code == 400 and '文件夹不存在' in r.json()['detail']


def test_the_api_imports_the_file_the_dialog_picks_and_never_replaces_a_preset(monkeypatch, tmp_path):
    presets.save('朋友的', {'style': 'loops'})
    f = write_file(tmp_path / 'p.json', {'format': presets.FORMAT, 'version': 1, 'name': '朋友的', 'params': TWO_LAYERS})
    answers = []
    monkeypatch.setattr(server, '_ask_preset_open', lambda: answers.pop(0))
    c = TestClient(server.app)
    answers.append(None)
    assert c.post('/api/look/presets/import').json() == {'cancelled': True}
    answers.append(f)
    r = c.post('/api/look/presets/import')
    body = r.json()
    assert r.status_code == 200 and body['imported'] == '朋友的 (2)' and body['renamed'] is True
    assert [p['name'] for p in body['presets']] == ['朋友的', '朋友的 (2)']
    assert body['presets'][0]['params']['style'] == 'loops'                              # still as it was
    assert body['presets'][1]['params']['layers'][0]['style'] == 'grain'
    assert settings.get('preset_dir') == str(tmp_path)
    answers.append(write_file(tmp_path / 'bad.json', '{"format": "other"}'))
    r = c.post('/api/look/presets/import')
    assert r.status_code == 400 and '这不是预设文件' in r.json()['detail']
    assert len(c.get('/api/look/presets').json()['presets']) == 2
