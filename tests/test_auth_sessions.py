import unittest

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.db_conf import Base
from crud.users import change_password, create_token, get_user_by_token
from models.users import User, UserToken
from utils.security import get_hash_password


class AuthSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        @event.listens_for(self.engine.sync_engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with self.sessions() as session:
            session.add(User(id=1, username="writer", password=get_hash_password("old-password")))
            await session.commit()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_login_creates_independent_sessions(self):
        async with self.sessions() as session:
            first = await create_token(session, 1)
            second = await create_token(session, 1)
            self.assertNotEqual(first, second)
            self.assertIsNotNone(await get_user_by_token(session, first))
            self.assertIsNotNone(await get_user_by_token(session, second))
            tokens = list((await session.scalars(select(UserToken))).all())
            self.assertEqual(len(tokens), 2)

    async def test_password_change_revokes_other_sessions(self):
        async with self.sessions() as session:
            current = await create_token(session, 1)
            other = await create_token(session, 1)
            user = await session.get(User, 1)
            self.assertTrue(user)
            self.assertTrue(await change_password(session, user, "old-password", "new-password", current))
            self.assertIsNotNone(await get_user_by_token(session, current))
            self.assertIsNone(await get_user_by_token(session, other))
            self.assertIsNotNone(user.updated_at)


if __name__ == "__main__":
    unittest.main()
