import asyncio
from sqlalchemy.future import select
from app.database.session import async_session
from app.models.category import Category

CATEGORIES_SEED = [
    {
        "id": "bike-repair",
        "title": "Bike Repair",
        "description": "On-demand professional bike repair and service at your doorstep.",
        "image": "https://images.unsplash.com/photo-1485965120184-e220f721d03e?auto=format&fit=crop&w=600&q=80",
        "icon": "motorcycle",
        "isActive": True
    },
    {
        "id": "car-repair",
        "title": "Car Repair & Service",
        "description": "Professional car inspection, servicing, and repair by certified mechanics.",
        "image": "https://images.unsplash.com/photo-1486006920555-c77dce18193b?auto=format&fit=crop&w=600&q=80",
        "icon": "directions_car",
        "isActive": True
    },
    {
        "id": "mobile-repair",
        "title": "Mobile Repair",
        "description": "Fast and reliable repair for screens, batteries, and software issues.",
        "image": "https://images.unsplash.com/photo-1581092918056-0c4c3acd3789?auto=format&fit=crop&w=600&q=80",
        "icon": "phone_android",
        "isActive": True
    },
    {
        "id": "laptop-repair",
        "title": "Laptop Repair",
        "description": "Expert hardware and software solutions for all laptop brands.",
        "image": "https://images.unsplash.com/photo-1588702547919-26089e690eca?auto=format&fit=crop&w=600&q=80",
        "icon": "laptop",
        "isActive": True
    },
    {
        "id": "ac-repair",
        "title": "AC Repair & Service",
        "description": "Keep cool with AC filter cleaning, gas refill, and installation.",
        "image": "https://images.unsplash.com/photo-1621905252507-b354bc25edac?auto=format&fit=crop&w=600&q=80",
        "icon": "ac_unit",
        "isActive": True
    },
    {
        "id": "electrician",
        "title": "Electrician",
        "description": "Safe and reliable electrical installations, repairs, and wiring.",
        "image": "https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=600&q=80",
        "icon": "bolt",
        "isActive": True
    },
    {
        "id": "plumber",
        "title": "Plumber",
        "description": "Leak repairs, pipe fittings, and toilet repairs done by experts.",
        "image": "https://images.unsplash.com/photo-1504328345606-18bbc8c9d7d1?auto=format&fit=crop&w=600&q=80",
        "icon": "plumbing",
        "isActive": True
    },
    {
        "id": "carpenter",
        "title": "Carpenter",
        "description": "Furniture repairs, custom assemblies, and woodwork.",
        "image": "https://images.unsplash.com/photo-1534224039826-c7a0dea0e66a?auto=format&fit=crop&w=600&q=80",
        "icon": "handyman",
        "isActive": True
    },
    {
        "id": "home-cleaning",
        "title": "Home Cleaning",
        "description": "Deep home cleaning, kitchen cleaning, and bathroom disinfection.",
        "image": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=600&q=80",
        "icon": "cleaning_services",
        "isActive": True
    },
    {
        "id": "packers-movers",
        "title": "Packers & Movers",
        "description": "Hassle-free packing and relocation services for home and office.",
        "image": "https://images.unsplash.com/photo-1600585154526-990dced4db0d?auto=format&fit=crop&w=600&q=80",
        "icon": "local_shipping",
        "isActive": True
    },
    {
        "id": "home-tutor",
        "title": "Home Tutor",
        "description": "Personalized educational tutoring for school students at home.",
        "image": "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=600&q=80",
        "icon": "school",
        "isActive": True
    },
    {
        "id": "business-registration",
        "title": "Business Registration & Local Business Listing",
        "description": "Get your business registered and listed on local mapping platforms.",
        "image": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=600&q=80",
        "icon": "business",
        "isActive": True
    }
]

async def seed_categories_asyncpg():
    import asyncpg
    from app.core.config import settings
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        for cat_data in CATEGORIES_SEED:
            existing = await conn.fetchval(
                "SELECT id FROM categories WHERE id=$1 OR title=$2", 
                cat_data["id"], cat_data["title"]
            )
            if not existing:
                await conn.execute("""
                    INSERT INTO categories (id, title, description, image, icon, "isActive")
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, cat_data["id"], cat_data["title"], cat_data["description"], cat_data["image"], cat_data["icon"], cat_data["isActive"])
                print(f"[SEED-FALLBACK] Seeded category: {cat_data['title']}")
            else:
                await conn.execute("""
                    UPDATE categories 
                    SET title=$2, description=$3, image=$4, icon=$5, "isActive"=$6
                    WHERE id=$1
                """, cat_data["id"], cat_data["title"], cat_data["description"], cat_data["image"], cat_data["icon"], cat_data["isActive"])
        print("[SEED-FALLBACK] Categories seeding completed successfully via direct asyncpg.")
    except Exception as e:
        print(f"[SEED-FALLBACK] Categories seeding failed: {e}")
    finally:
        await conn.close()

async def seed_categories():
    print("[SEED] Seeding categories if they do not exist...")
    try:
        async with async_session() as session:
            try:
                for cat_data in CATEGORIES_SEED:
                    stmt = select(Category).where((Category.id == cat_data["id"]) | (Category.title == cat_data["title"]))
                    res = await session.execute(stmt)
                    existing = res.scalar_one_or_none()
                    
                    if not existing:
                        new_cat = Category(
                            id=cat_data["id"],
                            title=cat_data["title"],
                            description=cat_data["description"],
                            image=cat_data["image"],
                            icon=cat_data["icon"],
                            isActive=cat_data["isActive"]
                        )
                        session.add(new_cat)
                        print(f"[SEED] Added category: {cat_data['title']}")
                    else:
                        existing.title = cat_data["title"]
                        existing.description = cat_data["description"]
                        existing.image = cat_data["image"]
                        existing.icon = cat_data["icon"]
                        session.add(existing)
                await session.commit()
                print("[SEED] Categories seeding completed successfully via SQLAlchemy.")
            except Exception as e:
                await session.rollback()
                raise e
    except Exception as e:
        print(f"[SEED] SQLAlchemy seeding failed, trying direct asyncpg fallback: {e}")
        await seed_categories_asyncpg()

if __name__ == "__main__":
    asyncio.run(seed_categories())
