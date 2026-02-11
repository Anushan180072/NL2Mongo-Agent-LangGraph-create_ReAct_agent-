from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from .toolkit import MongoDBDatabaseToolkit
from .database import MongoDBDatabase
from langchain_google_genai import ChatGoogleGenerativeAI

from pymongo import MongoClient
from bson.objectid import ObjectId
from typing import Any, Dict, List, Union

from langchain import hub
from langgraph.prebuilt import create_react_agent
from .prompt import MONGODB_AGENT_SYSTEM_PROMPT

from datetime import datetime, timezone, timedelta
from dateutil.parser import parse
import pytz
import tzlocal
import json

from langchain.tools import tool

from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.store.mongodb import MongoDBStore

from dotenv import load_dotenv
import os
from google.api_core.exceptions import ResourceExhausted, InternalServerError 
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES 
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
AI_STRING = os.getenv("AI_CONNECTION_STRING")
DEV_STRING = os.getenv("MONGODB_LOCAL_CONNECTION_STRING")
db_name = os.getenv("DATABASE_NAME")

class MongoConnection:
    _clients = {}

    @classmethod
    def get_client(cls, uri):
        if uri not in cls._clients:
            cls._clients[uri] = MongoClient(uri)
        return cls._clients[uri]

def current_date(timezone_name: str):
    """
    Function to create a get_current_date_time tool instance
    configured with a specific timezone.
    """
    @tool

    def get_current_date_time() -> Dict[str, str]:
        """
        Gets the current date and time context, including local time, UTC time,
        and the start and end date times of the current day in UTC.
    
        This tool is useful for answering questions or performing queries that
        require knowledge of the current date and time, such as filtering data
        for "today", "yesterday", "tomorrow", "this year", "last year", "this month", "last month", "next month", "this week", "last week", "after or before some days" etc.
    
        This tool is useful for converting date to UTC format.
    
        Returns:
            A dictionary containing the following time strings:
            - 'local_timezone': The name of the configured local timezone.
            - 'local_datetime': The current local date and time in ISO format.
            - 'utc_datetime': The current UTC date and time in ISO format.
            - 'start_of_day_utc': The start of the current day in UTC ISO format.
            - 'end_of_day_utc': The end of the current day in UTC ISO format.
            - 'start_of_yesterday_utc': The start of the yesterday in UTC format
            - 'start_of_tomorrow_utc': The start of the tomorrow in UTC format
            - 'current_month': The name of the present month (e.g., "May").
            - 'current_year': The current year (e.g., "2025").
        """
        try:
            local_tz = pytz.timezone(timezone_name)
    
            local_dt = datetime.now(local_tz)
            local_time_iso = local_dt.isoformat()
    
            #utc_dt = local_dt.astimezone(pytz.utc)
            #utc_time_iso = utc_dt.isoformat()
    
            start_of_day_local = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day_local = local_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    
            start_of_day_utc = start_of_day_local.astimezone(timezone.utc)
            end_of_day_utc = end_of_day_local.astimezone(timezone.utc)
    
            start_of_day_utc_iso = start_of_day_utc.isoformat()
            end_of_day_utc_iso = end_of_day_utc.isoformat()
    
            start_of_yesterday_utc_iso = (start_of_day_utc - timedelta(days=1)).isoformat()
            start_of_tomorrow_utc_iso = (start_of_day_utc + timedelta(days=1)).isoformat()
    
            current_month = local_dt.strftime("%B")
            current_year = str(local_dt.year)
    
            return {
                'local_timezone': timezone_name,
                'local_datetime': local_time_iso,
                #'utc_datetime': utc_time_iso,
                'start_of_day_utc': start_of_day_utc_iso,
                'end_of_day_utc': end_of_day_utc_iso,
                'start_of_yesterday_utc': start_of_yesterday_utc_iso,
                'start_of_tomorrow_utc': start_of_tomorrow_utc_iso,
                'current_month': current_month,
                'current_year': current_year
            }
    
        except Exception as e:
            return {"error": f"Could not generate time context: {e}"}
        
    return get_current_date_time

@tool
def convert_date_to_utc(date_input: str, local_timezone_name: str) -> Dict[str, str]:
    """
    Calculates the start of a given date(in string) in a specified local timezone
    and then converts that specific moment to UTC.

    This tool is crucial to create queries related to dates to convert given date to UTC equivalent of given local timezone.

    For example, for June 2, 2025 in Asia/Kolkata (UTC+05:30):
    - Converted to UTC, this specific moment is 2025-06-01T18:30:00 UTC.

    For June 2, 2025 in America/New_York (UTC-04:00 during DST):
    - Converted to UTC, this specific moment is 2025-06-02T04:00:00 UTC.

    Args:
        date_input (str): The date in string format only to use for calculating the start of the day in UTC
        local_timezone_name (str): The IANA timezone name (e.g., "Asia/Kolkata", "America/New_York").

    Returns:
        Dict[str, str]: A dictionary containing:
            - 'utc_start_of_day': The converted start of the day in UTC (ISO format, with +00:00 offset).
            - 'error': (Optional) An error message if processing fails.
    """
    original_input_str = f"Date: {date_input}, Timezone: {local_timezone_name}"
    try:
        local_date = parse(date_input)
        local_tz = pytz.timezone(local_timezone_name)
        local_start_of_day = local_date.replace(hour=0, minute=0, second=0, microsecond=0)
        localized_start_of_day = local_tz.localize(local_start_of_day, is_dst=None)

        utc_start_of_day = localized_start_of_day.astimezone(timezone.utc)

        return {
            'utc_start_of_day': utc_start_of_day.isoformat()
        }

    except pytz.exceptions.UnknownTimeZoneError:
        return {
            'original_input': original_input_str,
            'error': f"Unknown timezone: '{local_timezone_name}'. Please provide a valid IANA timezone name (e.g., 'America/New_York', 'Asia/Kolkata')."
        }
    except Exception as e:
        return {
            'original_input': original_input_str,
            'error': f"Could not process input to determine local start of day in UTC. Error: {e}"
        }

def pre_model_hook(state):
    """
    A LangGraph pre-model hook to trim the messages sent to the LLM.
    This implementation also OVERWRITES the persisted history in the checkpointer,
    effectively keeping only the trimmed portion.
    """
    if "messages" not in state or not isinstance(state["messages"], list):
        print("Warning: 'messages' key not found or not a list in state for pre_model_hook.")
        return state 
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last", 
        token_counter=len,
        #token_counter=count_tokens_approximately, 
        max_tokens=25, 
        start_on="human",
        end_on=("human", "tool"),
    )
    #print(f"Trimmed messages for LLM input. Original full history: {len(state['messages'])}, Trimmed (and to be saved) count: {len(trimmed_messages)}")
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)] + trimmed_messages}


API_KEYS=["AIzaSyALcvMdgeTfG5SZEdizKW31s3w_lilfEMY", "AIzaSyBtlOIeAoi3XnYQmV_rX2YavcfJAtbsQXw", "AIzaSyCFoRdjykZyjUqfSvYRtTO8ZFhfu5z1gbw","AIzaSyCDjY8RlU3LbIcc6TeIBKncEBcpNPtYw54"]
if not API_KEYS:
    raise ValueError("No API keys found in the 'API_KEYS' list. Please add at least one key.")

current_api_key_index = 0
llm_instances = {}

def get_llm_instance():
    global current_api_key_index
    current_key = API_KEYS[current_api_key_index]
    if current_key not in llm_instances:
        llm_instances[current_key] = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=current_key, temperature=0.2, thinking_budget=-1)
    else:
        print(f"Reusing existing LLM instance for key: {current_key[-5:]}...")
           
    return llm_instances[current_key] 


llm = get_llm_instance()
AI_client = MongoConnection.get_client(uri=AI_STRING)
memory = MongoDBSaver(AI_client)
client = MongoConnection.get_client(uri=DEV_STRING)
data_base = client[db_name]
SCHEMA_CACHE = {}

app = FastAPI(title="MongoDB Query Agent", description="API to interact with Kodefast MongoDB using a LangChain agent.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
class QueryRequest(BaseModel):
    connection_id: str
    question: str
    timezone: str = "Asia/Calcutta" 
    user_id: str

@app.post("/")
async def query_agent(request: QueryRequest):
    global llm
    global current_api_key_index
    max_retries = len(API_KEYS) 
    retries = 0
    company_id_str = str(request.connection_id)
    schema_string = SCHEMA_CACHE.get(company_id_str)
    if schema_string:
        pass
    else:
        entities_cursor = data_base.entity.find(
            {"company_id": ObjectId(request.connection_id), "status": "ACTIVE"},
            {"name": 1, "templates.template_id": 1}
        )
        
        
        entity_template_map = {}
        all_template_ids = set()
        
        for entity in entities_cursor:
            name = entity.get("name")
            templates = entity.get("templates", [])
            template_ids = [tpl.get("template_id") for tpl in templates if tpl.get("template_id")]
            if template_ids:
                entity_template_map[name] = template_ids
                all_template_ids.update(template_ids)
        
        
        template_cursor = data_base.templates.find(
            {"_id": {"$in": list(all_template_ids)}, "status": "ACTIVE"},
            {
                "_id": 1,
                "sections.fields.key": 1,
                "sections.fields.inputType": 1,
                "sections.fields.data_table_columns.key": 1,
                "sections.fields.data_table_columns.inputType": 1
            }
        )
        
        
        template_fields_map = {}
        
        for doc in template_cursor:
            template_id = str(doc["_id"])
            fields_list = []
        
            for section in doc.get("sections", []):
                for field in section.get("fields", []):
                    parent_key = field.get("key")
                    parent_type = field.get("inputType", "string")
        
                    if parent_type == "ENTITY_TABLE":
                        continue
        
                    if parent_key:
                        suffix = "/name" if parent_type == "ENTITY" else ""
                        fields_list.append(f"templates_fields_data.{template_id}#{parent_key}{suffix}: {parent_type}")
        
                    for col in field.get("data_table_columns", []):
                        col_key = col.get("key")
                        col_type = col.get("inputType", "string")
                        if col_type == "ENTITY_TABLE":
                            continue
                        if col_key:
                            suffix = "/name" if col_type == "ENTITY" else ""
                            fields_list.append(
                                f"templates_fields_data.{template_id}#{parent_key}.{col_key}{suffix}: {col_type}"
                            )
        
            template_fields_map[template_id] = fields_list
        
        
        result = {}
        
        for entity_name, template_ids in entity_template_map.items():
            entity_fields = []
            for tpl_id in template_ids:
                tpl_id_str = str(tpl_id)
                entity_fields.extend(template_fields_map.get(tpl_id_str, []))
            result[entity_name] = entity_fields

        schema_string = json.dumps(result, indent=2)
        SCHEMA_CACHE[company_id_str] = schema_string                
        

    while retries < max_retries:
        try:      
            db = MongoDBDatabase(client=client, database=db_name, include_collections = ["entities_data"], schema = schema_string )
            toolkit = MongoDBDatabaseToolkit(db=db, llm=llm)
            db_tools = toolkit.get_tools()
            time_tool = current_date(request.timezone)
            tools = db_tools + [time_tool, convert_date_to_utc]
        
            system_message = MONGODB_AGENT_SYSTEM_PROMPT.format(company_id=request.connection_id, local_timezone=request.timezone)
            # Create agent
            agent_executor = create_react_agent(
                llm, tools, state_modifier=system_message, pre_model_hook=pre_model_hook, checkpointer=memory
            )
        
            user_query = f"**USER_QUESTION**:{request.question}? \n**RULES**:For general question like HI, HOW ARE YOU, just give general answers. For other queries make sure that, company should be ObjectId(\"{request.connection_id}\"). PLEASE get the schema by using given tools. "
        
            events = agent_executor.stream(
                {"messages": [("user", user_query)]},
                {"configurable": {"thread_id": request.user_id}},
                stream_mode="values",
                
            )
        
            output = []
            for event in events:
                #event["messages"][-1].pretty_print()
                output.append(event["messages"][-1].content)
            return {"answer": output[-1]}
        except (ResourceExhausted, InternalServerError) as e:
            current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
            retries += 1
            llm = get_llm_instance()
            if retries < max_retries:
                print(f"Retrying with new key: {API_KEYS[current_api_key_index][-5:]}...")
                continue 
            else:
                raise HTTPException(status_code=500, detail="All API keys exhausted or failed. Please check your API quotas.")
        
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=404,detail=("Sorry I am unable get the results. There may be no data related to you query. Or please give your query more clear and exact keyword and values.",str(e)))
