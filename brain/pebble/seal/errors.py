from ..selfstore.sealed import SelfIsSealed


class SealError(Exception):
    pass


class CryptoMissing(SealError, RuntimeError):
    pass


class NoSelf(SealError):
    pass


class NotSealed(SealError):
    pass


class AlreadySealed(SealError):
    pass


class WeakPassword(SealError):
    pass


class WrongPassword(SealError):
    pass


class TooManyTries(WrongPassword):
    def __init__(self, message: str, wait_s: float = 0.0):
        super().__init__(message)
        self.wait_s = wait_s


class NoOwnerLock(SealError):
    pass


class CardError(SealError):
    pass


class DeviceKeyDamaged(SealError):
    pass


class KeystoreUnavailable(SealError):
    pass


class RoomError(SealError):
    pass


class NoRoom(RoomError):
    pass


class NoDeviceKey(SelfIsSealed, SealError):
    pass


class WrongDeviceKey(NoDeviceKey):
    pass
