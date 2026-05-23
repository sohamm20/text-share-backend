import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import motor.motor_asyncio
from pymongo import ReturnDocument

# The connection string will be read directly from the MONGO_URI environment variable
MONGO_URI = os.getenv("MONGO_URI")

client = None
db = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    if not MONGO_URI:
        print("MONGO_URI environment variable not set. Falling back to in-memory mongomock-motor client.")
        from mongomock_motor import AsyncMongoMockClient
        client = AsyncMongoMockClient()
        db = client.get_database("fastapi_database")
    else:
        try:
            # Try connecting to the actual MongoDB Atlas instance
            client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            await client.admin.command('ping')
            db = client.get_database("fastapi_database")
            print("Successfully connected to MongoDB Atlas!")
        except Exception as e:
            print(f"MongoDB connection failed ({e}). Falling back to in-memory mongomock-motor client.")
            from mongomock_motor import AsyncMongoMockClient
            client = AsyncMongoMockClient()
            db = client.get_database("fastapi_database")
    yield
    if client:
        client.close()

app = FastAPI(title="FastAPI Boilerplate", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SetApiRequest(BaseModel):
    text: str

async def get_mex_id() -> int:
    # Retrieve all existing IDs sorted in ascending order
    cursor = db["text-share"].find({}, {"_id": 1}).sort("_id", 1)
    existing_ids = [doc["_id"] async for doc in cursor]
    
    # Find the smallest positive integer (starting from 1) not in the list
    mex = 1
    for val in existing_ids:
        if val == mex:
            mex += 1
        elif val > mex:
            break
    return mex

@app.post("/setapi", status_code=201)
async def set_api(payload: SetApiRequest):
    next_id = await get_mex_id()
    await db["text-share"].insert_one({"_id": next_id, "text": payload.text})
    return {"id": next_id, "text": payload.text}

@app.get("/getapi/{id}")
async def get_api(id: int):
    item = await db["text-share"].find_one({"_id": id})
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"text": item["text"]}

@app.get("/admin/items")
async def get_all_items():
    cursor = db["text-share"].find({}, {"_id": 1, "text": 1}).sort("_id", 1)
    items = []
    async for doc in cursor:
        items.append({"id": doc["_id"], "text": doc["text"]})
    return items

@app.delete("/admin/items/{id}")
async def delete_item(id: int):
    res = await db["text-share"].delete_one({"_id": id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": f"Successfully deleted item {id}"}

if __name__ == "__main__":
    # Start the Uvicorn server
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)