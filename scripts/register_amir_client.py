import asyncio
from datetime import datetime
from app.core.database import async_session_factory
from app.models_multitenant import Client
from app.auth_multitenant import hash_password


async def setup_amir_client():
    async with async_session_factory() as session:
        # Check if client with ID 1 exists
        client = await session.get(Client, 1)

        # We'll set the password to amir123
        hashed = await hash_password("amir123")

        if client:
            print("Client 1 exists. Updating details to amir@gmail.com...")
            client.client_code = "amir"
            client.name = "امیر"
            client.full_name = "امیر"
            client.email = "amir@gmail.com"
            client.username = "amir"
            client.hashed_password = hashed
            client.status = "active"
            client.subscription_start_date = None
            client.subscription_end_date = datetime(2030, 1, 1)  # Active until 2030
            session.add(client)
        else:
            print("Client 1 does not exist. Creating new client amir@gmail.com...")
            client = Client(
                id=1,
                client_code="amir",
                name="امیر",
                full_name="امیر",
                email="amir@gmail.com",
                phone="09120000000",
                hashed_password=hashed,
                status="active",
                access_level="standard",
                username="amir",
                subscription_start_date=None,
                subscription_end_date=datetime(2030, 1, 1),
            )
            session.add(client)

        await session.commit()
        print("Client amir@gmail.com registered and updated successfully!")


if __name__ == "__main__":
    asyncio.run(setup_amir_client())
