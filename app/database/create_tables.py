import asyncio
import asyncpg
from app.core.config import settings

async def main():
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    
    print("Connecting to database to apply manual migration...")
    conn = await asyncpg.connect(url)
    try:
        # 1. Create categories table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(100) UNIQUE NOT NULL,
                description VARCHAR(1000),
                image VARCHAR(500),
                icon VARCHAR(100),
                "isActive" BOOLEAN DEFAULT TRUE NOT NULL
            );
        """)
        print("Table 'categories' created or already exists.")
        
        # 2. Add isInstant column to bookings if not exists
        has_is_instant = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name='bookings' AND column_name='isInstant'
            );
        """)
        if not has_is_instant:
            await conn.execute('ALTER TABLE bookings ADD COLUMN "isInstant" BOOLEAN DEFAULT FALSE NOT NULL;')
            print("Added 'isInstant' column to 'bookings' table.")
        else:
            print("'isInstant' column already exists in 'bookings' table.")
            
        # 3. Update alembic_version table to '0003'
        await conn.execute("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY);")
        version = await conn.fetchval("SELECT version_num FROM alembic_version LIMIT 1;")
        if not version:
            await conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0003');")
            print("Set alembic_version to '0003'")
        elif version != '0003':
            await conn.execute("UPDATE alembic_version SET version_num = '0003';")
            print(f"Updated alembic_version from '{version}' to '0003'")
        else:
            print("alembic_version is already at '0003'")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
