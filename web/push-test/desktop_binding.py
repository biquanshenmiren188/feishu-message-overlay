"""Per-code desktop policies, without phone pairing or subscription writes."""
import re
import threading
from desktop_rules import DesktopRules


def unrestricted():
    return dict(pushBinding=dict(protocol=1, bound=False, canManage=False),
                desktopRules=dict(revision=0, messages={}, cards={}, desktopEnabled=True, cardsEnabled=True))


class DesktopProfiles:
    def __init__(self, profiles, legacy):
        self.profiles = profiles
        self.legacy = legacy
        self.policies = {'legacy': legacy}
        self.lock = threading.RLock()

    def policy(self, account):
        # Account identity comes exclusively from the server registry/token.
        with self.lock:
            if self.profiles.accounts.get(account.profile_id) is not account:
                raise ValueError('推送方案不可用')
            if account.profile_id not in self.policies:
                self.policies[account.profile_id] = DesktopRules(account.directory, self.legacy.feed, self.legacy.cards)
            return self.policies[account.profile_id]

    def account(self, data):
        client = data.get('client')
        if not isinstance(client, str) or not re.fullmatch('[a-f0-9]{16}', client):
            raise ValueError('客户端身份无效')
        return self.profiles.desktop_account(data.get('pushCode'), 'desktop:'+client)

    def state(self, data):
        if set(data) != {'pushCode', 'client'}:
            raise ValueError('桌面绑定请求无效')
        if data['pushCode'] == '':
            return unrestricted()
        account = self.account(data)
        return dict(pushBinding=dict(protocol=1, bound=True, canManage=True),
                    desktopRules=self.policy(account).evaluate())

    def coins(self, data):
        from coin_control import dispatch
        if set(data) != {'pushCode', 'client', 'request'} or not isinstance(data['request'], dict):
            raise ValueError('桌面绑定请求无效')
        account = self.account(data)
        return dispatch(self.policy(account), account, data['request'])
