import sys
from types import SimpleNamespace

sys.path.insert(0, '/backend')

from draw import draw

EPS = [SimpleNamespace(slug=f'{show}{i}', podcast_id=show, pub_ts=1_600_000_000 + i * 86400)
       for show in ('a', 'b') for i in range(30)]


def test_a_draw_is_stratified_reproducible_and_leaves_out_what_is_in():
    have = {'a0', 'a1', 'b29'}
    one, two = draw(EPS, have, 7, 2), draw(EPS, have, 7, 2)
    assert [e.slug for e, _ in one] == [e.slug for e, _ in two]
    assert len(one) == 12 and not have & {e.slug for e, _ in one}
    assert sorted(t.split()[0] for e, t in one if e.podcast_id == 'a') == ['début'] * 2 + ['milieu'] * 2 + ['récent'] * 2
