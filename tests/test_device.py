from types import SimpleNamespace

from stocking.sam import _runs_on, pick_device

CU128 = ['sm_75', 'sm_80', 'sm_86', 'sm_90', 'sm_100', 'sm_120']


def fake_torch(devices, arches=CU128, available=True):
    """devices: [(name, (major, minor), memory GB)]"""
    cuda = SimpleNamespace(
        is_available=lambda: available,
        get_arch_list=lambda: arches,
        device_count=lambda: len(devices),
        get_device_capability=lambda i: devices[i][1],
        get_device_properties=lambda i: SimpleNamespace(total_memory=devices[i][2] << 30),
        get_device_name=lambda i: devices[i][0],
    )
    return SimpleNamespace(cuda=cuda)


def test_a_kernel_runs_on_later_minor_versions_of_its_major():
    assert _runs_on(CU128, 8, 9)            # RTX 4090 on the sm_86 kernels
    assert _runs_on(CU128, 12, 0)           # RTX 50 series
    assert not _runs_on(CU128, 6, 1)        # Pascal: too old for this build
    assert not _runs_on(CU128, 7, 0)        # Volta: sm_75 is a later minor, it cannot run there
    assert not _runs_on(['compute_90'], 9, 0)


def test_pick_device_takes_the_biggest_card_that_can_run():
    t = fake_torch([('RTX 4090', (8, 9), 24), ('RTX 5060 Ti', (12, 0), 16)])
    assert pick_device(t) == ('cuda:0', 'RTX 4090')
    t = fake_torch([('GTX 1080 Ti', (6, 1), 11), ('RTX 3060', (8, 6), 12)])
    assert pick_device(t) == ('cuda:1', 'RTX 3060')


def test_pick_device_falls_back_to_the_cpu():
    assert pick_device(fake_torch([], available=False)) == ('cpu', 'CPU')
    assert pick_device(fake_torch([('GTX 1080', (6, 1), 8)])) == ('cpu', 'CPU')
