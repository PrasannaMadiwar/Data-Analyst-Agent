#------------------------------------------- Importing all dependencies ---------------------------------------------------
from dotenv import load_dotenv
import os
from daytona import Daytona, DaytonaConfig
from daytona import FileDownloadRequest
import base64
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import TypedDict, Literal, Annotated, List
from operator import add

load_dotenv()

#----------------------------------------- set-pu of daytona sandbox, text model and image model ------------------------------
config = DaytonaConfig(api_key=os.getenv("DAYTONA_API_KEY"))
daytona = Daytona(config)
sandbox = daytona.create()

from langchain_groq import ChatGroq
model = ChatGroq(model="openai/gpt-oss-120b")
image_model = ChatGroq(model_name="meta-llama/llama-4-scout-17b-16e-instruct")

#------------------------------------ Helping function to upload the respective csv on the sandbox -----------------------------
def upload_csv(local_path: str, remote_path: str = "data.csv"):
    """
    Upload a local CSV file into Daytona sandbox.
    """
    with open(local_path, "rb") as f:
        content = f.read()

    sandbox.fs.upload_file(content, remote_path)

#-------------------------------------------------- defining graph state ----------------------------------------------------
class Mystate(TypedDict):
    summary : Annotated[List[str], add]
    last_step : str
    final_analysis : str

#------------------------------------------------------ dataframe summury Node ---------------------------------------------
def csv_summary_node(state) -> Mystate:
    csv_path = "data.csv"
    summary_path = "summary.txt"

    code = f"""
import pandas as pd
import os

df = pd.read_csv("{csv_path}")

with open("{summary_path}", "w") as f:
    f.write("CSV SUMMARY REPORT\\n")
    f.write("="*50 + "\\n\\n")
    
    f.write(f"Shape: {{df.shape}}\\n\\n")
    
    f.write("Columns:\\n")
    for col in df.columns:
        f.write(f" - {{col}}\\n")
    f.write("\\n")
    
    f.write("Data Types:\\n")
    for col, dtype in df.dtypes.items():
        f.write(f" - {{col}}: {{dtype}}\\n")
    f.write("\\n")
    
    f.write("Missing Values:\\n")
    for col, count in df.isnull().sum().items():
        f.write(f" - {{col}}: {{count}}\\n")
    f.write("\\n")
    
    f.write("Statistical Summary:\\n")
    f.write(df.describe(include='all').to_string())

print("SUMMARY_CREATED")
"""

    response = sandbox.process.code_run(code)

    if response.exit_code != 0:
        raise RuntimeError(response.result)
    
    summary_path ="summary.txt"

    content = sandbox.fs.download_file(summary_path)
    state["summary"] = [content.decode("utf-8")]

    return state
#----------------------------------------------------- removing or filling null values Node --------------------------------
class NullCode(BaseModel):
    code: str = Field(
        description="Valid executable Python code that removes null values from data.csv and overwrites data.csv"
    )

null_parser = PydanticOutputParser(pydantic_object=NullCode)


null_prompt = PromptTemplate(
    template="""
        You are a professional data scientist.

        Your task:
        - Generate ONLY executable Python code.
        - The code must:
            1. Read 'data.csv'
            2. Remove null values intelligently based on the summary provided
            3. Overwrite the cleaned dataframe back into 'data.csv'
            4. Print "NULL_VALUES_REMOVED" at the end

        Rules:
        - Do NOT add explanations.
        - Do NOT wrap code in markdown.
        - Output must strictly follow the format instructions.
        - 

        Summary of dataset:
        {summary}

        {format_instructions}
""",
    input_variables=["summary"],
    partial_variables={
        "format_instructions": null_parser.get_format_instructions()
    }
)

model_null = null_prompt | model | null_parser

def remove_null(state:Mystate) -> Mystate:
    summary = state['summary']
    code = model_null.invoke({'summary':summary})
    generated_code = code.code

    generated_code = generated_code.encode().decode("unicode_escape")
    response = sandbox.process.code_run(generated_code)

    if response.exit_code != 0:
        raise RuntimeError(response.result)
    state['last_step'] = "removed null values"
    return state
  

#----------------------------------------------------- Encoding catogorical columns into numeric values Node ------------------
class EncodeCode(BaseModel):
    code: str = Field(
        description="Executable Python code that encodes categorical columns in data.csv, overwrites data.csv, and writes operation summary to summary.txt"
    )

encode_parser = PydanticOutputParser(pydantic_object=EncodeCode)


encode_prompt = PromptTemplate(
    template="""
        You are a professional data scientist.

        Generate ONLY raw executable Python code.

        Task:
        1. Read 'data.csv'
        2. Detect categorical columns automatically
        3. Encode categorical columns using Label Encoding
        4. Store encoding mappings in summary.txt
        5. Overwrite updated dataframe to data.csv
        6. Print "ENCODING_COMPLETED" at the end

        Requirements:
        - Use pandas and sklearn.preprocessing.LabelEncoder
        - Store encoding mappings like:
        {{
            "encoded_columns": [...],
            "mappings": {{
                "column_name": {{"category": encoded_value}}
            }}
        }}
        - Overwrite summary.txt
        - Do NOT escape newline characters
        - Do NOT wrap code in markdown
        - Output strictly valid Python


        Dataset Summary:
        {summary}

        {format_instructions}
        """,
    input_variables=["summary"],
    partial_variables={
        "format_instructions": encode_parser.get_format_instructions()
    }
)

model_encode = encode_prompt | model | encode_parser


def encode_cat(state:Mystate) -> Mystate:
    summary = state['summary']
    code = model_encode.invoke({'summary':summary})
    generated_code = code.code

    generated_code = generated_code.encode().decode("unicode_escape")
    response = sandbox.process.code_run(generated_code)

    if response.exit_code != 0:
        raise RuntimeError(response.result)
    state['last_step'] = "encoded columns"
    summary_path ="summary.txt"
    content = sandbox.fs.download_file(summary_path)
    state["summary"] = [content.decode("utf-8")]
    return state


#------------------------------------------------------- Creating various graphs and plots Node ---------------------------------
class PlotCode(BaseModel):
    code: str = Field(
        description="Executable Python code that generates multiple plots using matplotlib and seaborn and saves them in a folder named 'visualizations'"
    )

plot_parser = PydanticOutputParser(pydantic_object=PlotCode)

plot_prompt = PromptTemplate(
    template="""
        You are a professional data scientist.

        Generate executable Python code.

        Task:
        1. Read 'data.csv'
        2. Create multiple plots using matplotlib and seaborn
        3. Save all plots inside a folder named 'visualizations'

        Requirements:
        - Use matplotlib.pyplot as plt
        - Use seaborn as sns
        - Create the folder if it does not exist
        - Save each plot using plt.savefig()
        - Close each figure using plt.close()
        - Do NOT wrap code in markdown
        - Output strictly valid JSON following the format instructions

        Dataset Summary:
        {summary}

        {format_instructions}
        """,
    input_variables=["summary"],
    partial_variables={
        "format_instructions": plot_parser.get_format_instructions()
    }
)

model_plot = plot_prompt | model | plot_parser 

def create_plots(state:Mystate) -> Mystate:
    summary = state['summary']
    code = model_plot.invoke({'summary':summary})
    generated_code = code.code

    generated_code = generated_code.encode().decode("unicode_escape")
    response = sandbox.process.code_run(generated_code)

    if response.exit_code != 0:
        raise RuntimeError(response.result)
    state['last_step'] = "created graphs"

    return state

#-------------------------- generating analysis report using plots and all operation summary Node ------------------------
def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()        
    
def final_analysis(state:Mystate) -> Mystate:

    files = sandbox.fs.list_files("visualizations")
    plot_files = []

    for file in files:
        if not file.is_dir:  
            plot_files.append(f"visualizations/{file.name}")

    requests = [
    FileDownloadRequest(source=path)
    for path in plot_files]

    results = sandbox.fs.download_files(requests)

    os.makedirs("downloaded_plots", exist_ok=True)

    for result in results:
        if result.error:
            print(f"Error: {result.error}")
        elif result.result:
            filename = os.path.basename(result.source)
            local_path = os.path.join("downloaded_plots", filename)

            with open(local_path, "wb") as f:
                f.write(result.result)

            print(f"Saved: {local_path}") 

    
    folder_path = "downloaded_plots"
    image_messages = []
    image_count = 1

    for file in os.listdir(folder_path):
        if image_count > 5:
            break
        if file.lower().endswith((".jpg", ".jpeg", ".png")):
            full_path = os.path.join(folder_path, file)
            base64_img = encode_image(full_path)

            image_messages.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_img}"
                }
            })
            image_count += 1


    summ = state['summary']
    analysis_prompt = f"""
        You are a senior data analyst and statistical expert.

        Your task:
        Provide a detailed, structured analysis of the given graphs and plots.

        Requirements:

        1. Structure your analysis into clear sections:
        - Overview of dataset
        - Key trends observed
        - Patterns and distributions
        - Relationships between variables
        - Outliers or anomalies
        - Impact of preprocessing
        - Business or practical insights
        - Recommendations

        2. Use statistical reasoning wherever possible.
        3. Explain why patterns might exist.
        4. Comment on correlations, skewness, clusters, and variance if visible.
        5. Discuss how preprocessing steps influenced the results.
        5. Give proper output format 

        Preprocessing Summary:
        {summ} """

            
    message = HumanMessage(
        content=[
            {"type": "text", "text":analysis_prompt},
            *image_messages
        ]
    )

    response = image_model.invoke([message])
    
    return {
        "final_analysis": response.content
    }

#---------------------------------------------- Graph workflow creation -------------------------------------------------              
graph = StateGraph(Mystate)
graph.add_node("summary",csv_summary_node)
graph.add_node("remove_null",remove_null)
graph.add_node("encode_cat",encode_cat)
graph.add_node("create_plots",create_plots)
graph.add_node("final_analysis",final_analysis)

graph.add_edge(START,"summary")
graph.add_edge("summary","remove_null")
graph.add_edge("remove_null","encode_cat")
graph.add_edge("encode_cat","create_plots")
graph.add_edge("create_plots","final_analysis")
graph.add_edge("final_analysis",END)

workflow = graph.compile()              