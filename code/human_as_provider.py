import os
import os.path as osp
import re
import json
import argparse
import time
from functools import wraps
from tqdm import tqdm

from autogen import (
    GroupChat,
    UserProxyAgent,
    GroupChatManager,
    AssistantAgent,
    config_list_from_json
)


def simple_retry(max_attempts=10, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt < max_attempts - 1:
                        print(f"Attempt {attempt + 1} failed: {str(e)}. Retry in {delay} sec...")
                        time.sleep(delay)
                    else:
                        print(f"All {max_attempts} attempts Failed. Final error: {str(e)}")
                        raise
        return wrapper
    return decorator

import re
import json
import os.path as osp

def extract_final_section(chat_history, case_output_dir, section):
    """
    Extract specific part from chat history (e.g., Final History, Final Physical Examination, 
    Final Test, etc.) and save as JSON file.
    """
    # Define keywords and regular expressions to match w/ different formats
    patterns = {
        "Final History": [
            r'"Final\s*History"\s*:\s*"([^"]*)"',           # Match w/ "Final History": "content"
            r'"Final\s*History"\s*:\s*(\{[\s\S]*?\})',      # Match w/ "Final History": { JSON }
            r'Final\s*History\s*[:\s]\s*([^\n\{\}]+)',      # Match w/ Final History: content OR Final History content
            r'Final\s*History\s*[:\s]\s*\{([\s\S]*?)\}',    # Match w/ Final History: { JSON }
        ],
        "Final Physical Examination": [
            r'"Final\s*Physical\s*Examination"\s*:\s*"([^"]*)"',
            r'"Final\s*Physical\s*Examination"\s*:\s*(\{[\s\S]*?\})',
            r'Final\s*Physical\s*Examination\s*[:\s]\s*([^\n\{\}]+)',
            r'Final\s*Physical\s*Examination\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Final Test": [
            r'"Final\s*Test"\s*:\s*"([^"]*)"',
            r'"Final\s*Test"\s*:\s*(\{[\s\S]*?\})',
            r'Final\s*Test\s*[:\s]\s*([^\n\{\}]+)',
            r'Final\s*Test\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Final Diagnosis": [
            r'"Final\s*Diagnosis"\s*:\s*"([^"]*)"',
            r'"Final\s*Diagnosis"\s*:\s*(\{[\s\S]*?\})',
            r'Final\s*Diagnosis\s*[:\s]\s*([^\n\{\}]+)',
            r'Final\s*Diagnosis\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Differential Diagnosis": [
            r'"Differential\s*Diagnosis"\s*:\s*"([^"]*)"',
            r'"Differential\s*Diagnosis"\s*:\s*(\{[\s\S]*?\})',
            r'Differential\s*Diagnosis\s*[:\s]\s*([^\n\{\}]+)',
            r'Differential\s*Diagnosis\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Diagnostic Reasoning": [
            r'"Diagnostic\s*Reasoning"\s*:\s*"([^"]*)"',
            r'"Diagnostic\s*Reasoning"\s*:\s*(\{[\s\S]*?\})',
            r'Diagnostic\s*Reasoning\s*[:\s]\s*([^\n\{\}]+)',
            r'Diagnostic\s*Reasoning\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Final Updates During Physical Examination": [
            r'"Final\s*Updates\s*During\s*Physical\s*Examination"\s*:\s*"([^"]*)"',
            r'"Final\s*Updates\s*During\s*Physical\s*Examination"\s*:\s*(\{[\s\S]*?\})',
            r'Final\s*Updates\s*During\s*Physical\s*Examination\s*[:\s]\s*([^\n\{\}]+)',
            r'Final\s*Updates\s*During\s*Physical\s*Examination\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
        "Final Updates During Test": [
            r'"Final\s*Updates\s*During\s*Test"\s*:\s*"([^"]*)"',
            r'"Final\s*Updates\s*During\s*Test"\s*:\s*(\{[\s\S]*?\})',
            r'Final\s*Updates\s*During\s*Test\s*[:\s]\s*([^\n\{\}]+)',
            r'Final\s*Updates\s*During\s*Test\s*[:\s]\s*\{([\s\S]*?)\}',
        ],
    }

    if section not in patterns:
        print(f"Unknown extraction: {section}")
        return None

    extracted_data = None

    all_content = "\n".join([item.get("content", "") for item in chat_history])
    print(f"Extracting {section} content...")
    print(all_content)

    for pattern in patterns[section]:
        regex = re.compile(pattern, re.IGNORECASE | re.DOTALL)
        match = regex.search(all_content)
        if match:
            if match.lastindex == 2:
                string_value = match.group(1)
                json_object = match.group(2)
                if string_value:
                    extracted_data = string_value.strip()
                elif json_object:
                    try:
                        extracted_data = json.loads(json_object.strip())
                    except json.JSONDecodeError as e:
                        print(f"JSON error in decoding {section}: {str(e)}")
                        extracted_data = json_object.strip()
            elif match.lastindex == 1:
                potential_json = match.group(1).strip()
                if potential_json.startswith("{") and potential_json.endswith("}"):
                    try:
                        extracted_data = json.loads(potential_json)
                    except json.JSONDecodeError as e:
                        print(f"JSON error in decoding {section}: {str(e)}")
                        extracted_data = potential_json
                else:
                    extracted_data = potential_json
            print(f"Extracted {section}: {extracted_data}")
            break

    if extracted_data:
        file_suffix = section.replace("Final ", "").replace("Differential ", "").lower().replace(" ", "_")
        json_filename = f"final_{file_suffix}.json"  # e.g., final_history.json
        json_path = osp.join(case_output_dir, json_filename)
        with open(json_path, "w", encoding='utf-8') as file:
            json.dump({section: extracted_data}, file, indent=4, ensure_ascii=False)
        print(f"{section} saved to: {json_path}")
        return extracted_data
    else:
        print(f"Didn't find content matching {section}.")
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="Integrated Medagents Setting")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/OAI_Config_List.json",
        help="The LLM models configuration file.",
    )
    parser.add_argument(
        "--model_name_history",
        type=str,
        default="gpt-4o-mini",
        choices=["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct"],
        help="The LLM model for medical history.",
    )
    parser.add_argument(
        "--model_name_pe",
        type=str,
        default="gpt-4o-mini",
        choices=["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct"],
        help="The LLM model for physical examination.",
    )
    parser.add_argument(
        "--model_name_test",
        type=str,
        default="gpt-4o-mini",
        choices=["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct"],
        help="The LLM model for diagostic tests.",
    )
    parser.add_argument(
        "--model_name_diagnosis",
        type=str,
        default="gpt-4o-mini",
        choices=["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct"],
        help="The LLM model for diagnosis.",
    )
    parser.add_argument(
        "--model_name_provider",
        type=str,
        default="gpt-4o-mini",
        choices=["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "qwen2.5-72b-instruct", "qwen2.5-32b-instruct", "qwen2.5-14b-instruct", "qwen2.5-7b-instruct"],
        help="The LLM model for the Provider Agent.",
    )
    parser.add_argument(
        "--times",
        type=int,
        default=1,
        choices=[1, 2, 3],
        help="An identifier for multiple runs.",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="output",
        help="Directory to save output files.",
    )
    parser.add_argument(
        "--num_specialists", type=int, default=1, help="Number of doctor agents."
    )
    parser.add_argument("--n_round", type=int, default=50, help="Number of chat rounds.")
    parser.add_argument(
        "--data_dir",
        type=str,
        default="data",
        help="The root directory of the data folders.",
    )

    args = parser.parse_args()
    return args

@simple_retry(max_attempts=10, delay=1)
def history_gathering(args, subfolder, case_output_dir, model_config_history, model_config_provider):
    """
    Stage 1: History Gathering
    """
    # Paths
    initial_info_path = osp.join(subfolder, 'initial_information.json')
    with open(initial_info_path, 'r', encoding='utf-8') as f:
        case_presentation = f.read()

    conversation_path = osp.join(case_output_dir, "history_conversation.json")
    final_history_path = osp.join(case_output_dir, "final_history.json")

    if osp.exists(conversation_path) and osp.exists(final_history_path):
        print(f"History files already exist in {case_output_dir}. Skip history gathering.")
        return

    user_proxy = UserProxyAgent(
        name="Admin",
        system_message="A human admin doctor.",
        code_execution_config=False,
        human_input_mode="NEVER",
    )

    Docs = []
    for index in range(args.num_specialists):
        name = f"Doctor{index}"
        doc_system_message = f"""
Medical Doctor {index}. You are a Doctor Agent specialized in acquiring and analyzing a patient's medical history. 
Your sole responsibility is to gather comprehensive details about the patient's history to understand their health background better. 
You should ask specific, targeted questions and reason about what to ask next based on the feedback you receive.

Primary Objectives:
- Determine necessary inquiries and formulate specific, relevant questions to acquire patient's medical history information.
- Engage in iterative information gathering through dialogue with the patient.
- Assess when sufficient information has been obtained to cease further inquiries.

Constraints:
- Focus exclusively on medical history. Do not perform examinations, order tests, make diagnoses, or suggest treatments.
- May inquire about past examinations, test results, diagnoses, and treatments.
- Ensure each question is directly related to obtaining the patient's medical history.
- Ask specific questions (e.g., "Do you have a history of hypertension?") rather than broad ones (e.g., "Do you have any other diseases?").

Interaction Process:
- Initiate inquiry with specific questions about the patient's medical history.
- Receive and analyze feedback from the patient.
- Determine the next set of specific questions based on this analysis.
- Continue the cycle until sufficient information is gathered.

Guidelines:
- Form your diagonsis hypothesis, you might form serveral hypothesis, ask questions around these hypothesis
- Formulate clear, specific, and relevant questions.
- Adapt questioning based on responses and feedback.

For each inquiry, use the following format:
{{
    "doctor_reasoning": "Doctor's reasoning based on current information",
    "doctor_action": "Doctor's question to the patient, use second-person phrase"
}}

When all necessary information has been gathered, present the complete history in this format:
{{
    "Final History": "[patient's medical history]"
}}

Important note: sometimes you will continuously not receive feedback for the information you ask for, you should end the conversation and continue to summarize. If you do not have any informative information for either category, you can conclude "no valid information has been gathered".
you are interacting with patient, please use simple and easy-to-understand language and communication methods.
After you provide final history, it is your duty to reply with "TERMINATE" to end the conversation.
"""
        Doc = AssistantAgent(
            name=name,
            llm_config=model_config_history,
            system_message=doc_system_message,
        )
        Docs.append(Doc)

    provider_system_message = f"""
You do nothing, remain silent, output nothing."""

    provider = AssistantAgent(
        name="Assistant",
        llm_config=model_config_provider,
        system_message=provider_system_message,
        human_input_mode="ALWAYS",
    )

    groupchat = GroupChat(
        agents=[user_proxy] + Docs + [provider],
        messages=[],
        max_round=args.n_round,
        speaker_selection_method="round_robin"
    )
    time.sleep(5)

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=model_config_history,
        is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    )

    message = f"""
Here is a patient case for analysis, ask about patient history and provide the final patient history.

{case_presentation}
"""

    output = user_proxy.initiate_chat(
        manager,
        message=message,
    )

    with open(conversation_path, "w", encoding='utf-8') as file:
        json.dump(output.chat_history, file, indent=4, ensure_ascii=False)
    print(f"History conversation saved to: {conversation_path}")

    extracted_data = extract_final_section(output.chat_history, case_output_dir, "Final History")

    if not extracted_data:
        print(f"'Final History' not found, unable to save to {final_history_path}")
    else:
        # Save Final History
        with open(final_history_path, "w", encoding='utf-8') as file:
            json.dump({"Final History": extracted_data}, file, indent=4, ensure_ascii=False)
        print(f"Final History saved to: {final_history_path}")

@simple_retry(max_attempts=10, delay=1)
def pe_gathering(args, subfolder, case_output_dir, model_config_pe, final_history_path, model_config_provider):
    """
    Stage 2: Physical Examination Gathering
    """
    conversation_path = osp.join(case_output_dir, "pe_conversation.json")
    final_pe_path = osp.join(case_output_dir, "final_physical_examination.json")
    final_updates_pe_path = osp.join(case_output_dir, "final_updates_during_physical_examination.json")  

    if osp.exists(conversation_path) and osp.exists(final_pe_path):
        print(f"Physical examination files already exist in {case_output_dir}. Skip physical examination gathering.")
        return

    with open(final_history_path, 'r', encoding='utf-8') as f:
        final_history = json.load(f).get("Final History", "")

    user_proxy = UserProxyAgent(
        name="Admin",
        system_message="A human admin doctor.",
        code_execution_config=False,
        human_input_mode="NEVER",
    )

    Docs = []
    for index in range(args.num_specialists):
        name = f"Doctor{index}"
        doc_system_message = f"""
Medical Doctor {index}. You are a Doctor Agent specialized in acquiring and analyzing a patient's physical examination. 
Your sole responsibility is to gather comprehensive details about the patient's physical examination that would be helpful in reaching the final diagnosis, based on the patient history provided to you.
You should ask specific, targeted questions and reason about what to ask next based on the feedback you receive.

Primary Objectives:
- Determine necessary inquiries and formulate specific, relevant questions to acquire patient's physical examination information.
- Engage in iterative information gathering through dialogue with the patient.
- Assess when sufficient information has been obtained to cease further inquiries.

Constraints:
- Focus exclusively on physical examinations. Do not perform lab tests, radiographic tests, or other tests, do not make diagnoses, or suggest treatments.
- Ensure each question is directly related to obtaining the patient's physical examination.
- Ask specific questions (e.g., "Is there tenderness in the left lower quadrant of the abdomen?") rather than broad ones (e.g., "What is the result for abdominal physical examination?").
- Do not ask questions that are related to the patient's lab tests, radiographic tests and other diagnostic tests that are not categorized as physcial examination.
- Do not provide treatment recommendations.

Interaction Process:
- Initiate inquiry with specific questions about the patient's physical examination.
- Receive and analyze feedback from the patient.
- Determine the next set of specific questions based on this analysis.
- Continue the cycle until sufficient information is gathered.
- After you get results from physical examination, you can go back and ask for new information about patient history that has not been mentioned in the final history provided to you, if it is helpful in reaching diagnosis.

Guidelines:
- Form your diagonsis hypothesis, you might form serveral hypothesis, ask questions around these hypothesis 
- Formulate clear, specific, and relevant questions.
- Adapt questioning based on responses and feedback.

For each inquiry, use the following format:
{{
    "doctor_reasoning": "Doctor's reasoning based on current information",
    "doctor_action": "Doctor's question to the patient, use second-person phrase"
}}

When all necessary information has been gathered, present the complete physical examination in this format:
{{
    "Final Physical Examination": "[patient's physical examination results]"
}}

If you get new information from patient's history that is not provided in the patient record, please output the new information, use this format:
{{
    "Final Updates During Physical Examination": "[new information found regarding patient history, that is not included in the original patient record]"
}}

Important note: sometimes you will continuously not receive feedback for the information you ask for, you should end the conversation and continue to summarize. If you do not have any informative information for either category, you can conclude "no valid information has been gathered".
You are interacting with patient, please use simple and easy-to-understand language and communication methods.
After you provide final physical examination, it is your duty to reply with "TERMINATE" to end the conversation.

Here is the patient's record, based on these information you should determine what physical examination should be performed in the following conversation:
{final_history}
"""
        Doc = AssistantAgent(
            name=name,
            llm_config=model_config_pe,
            system_message=doc_system_message,
        )
        Docs.append(Doc)
        
    provider_system_message = f"""
You do nothing, remain silent, output nothing."""

    provider = AssistantAgent(
        name="Assistant",
        llm_config=model_config_provider,
        system_message=provider_system_message,
        human_input_mode="ALWAYS",
    )

    groupchat = GroupChat(
        agents=[user_proxy] + Docs + [provider],
        messages=[],
        max_round=args.n_round,
        speaker_selection_method="round_robin"
    )
    time.sleep(5)

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=model_config_pe,
        is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    )

    message = f"""
The doctor should ask for patient's physical examination results.
"""

    output = user_proxy.initiate_chat(
        manager,
        message=message,
    )

    with open(conversation_path, "w", encoding='utf-8') as file:
        json.dump(output.chat_history, file, indent=4, ensure_ascii=False)
    print(f"Physical Examination conversation saved to: {conversation_path}")

    extracted_data = extract_final_section(output.chat_history, case_output_dir, "Final Physical Examination")

    if not extracted_data:
        print(f"'Final Physical Examination' not found, unable to save to {final_pe_path}")
    else:
        # Save Final Physical Examination
        with open(final_pe_path, "w", encoding='utf-8') as file:
            json.dump({"Final Physical Examination": extracted_data}, file, indent=4, ensure_ascii=False)
        print(f"Final Physical Examination saved to: {final_pe_path}")

    extracted_updates_pe = extract_final_section(output.chat_history, case_output_dir, "Final Updates During Physical Examination")

    if not extracted_updates_pe:
        print(f"'Final Updates During Physical Examination' not found, unable to save to {final_updates_pe_path}")
    else:
        # Save Final Updates During Physical Examination
        with open(final_updates_pe_path, "w", encoding='utf-8') as file:
            json.dump({"Final Updates During Physical Examination": extracted_updates_pe}, file, indent=4, ensure_ascii=False)
        print(f"Final Updates During Physical Examination saved to: {final_updates_pe_path}")
        

@simple_retry(max_attempts=10, delay=1)
def test_gathering(args, subfolder, case_output_dir, model_config_test, final_history_path, final_pe_path, model_config_provider):
    """
    Stage 3: Test Gathering
    """
    conversation_path = osp.join(case_output_dir, "test_conversation.json")
    final_test_path = osp.join(case_output_dir, "final_test.json")
    final_updates_test_path = osp.join(case_output_dir, "final_updates_during_test.json")  
    
    if osp.exists(conversation_path) and osp.exists(final_test_path):
        print(f"Test files already exist in {case_output_dir}. Skip test gathering.")
        return

    with open(final_history_path, 'r', encoding='utf-8') as f:
        final_history = json.load(f).get("Final History", "")
    with open(final_pe_path, 'r', encoding='utf-8') as f:
        final_pe = json.load(f).get("Final Physical Examination", "")

    user_proxy = UserProxyAgent(
        name="Admin",
        system_message="A human admin doctor.",
        code_execution_config=False,
        human_input_mode="NEVER",
    )

    Docs = []
    for index in range(args.num_specialists):
        name = f"Doctor{index}"
        doc_system_message = f"""
Medical Doctor {index}. You are a Doctor Agent specialized in acquiring and analyzing a patient's test results, including lab tests, radiographic tests, and other diagnostic tests. 
Your sole responsibility is to gather comprehensive details about the patient's test results that would be helpful in reaching the final diagnosis, based on the patient's history and physical examination provided to you.
You should ask specific, targeted questions and reason about what to ask next based on the feedback you receive.

Primary Objectives:
- Determine necessary inquiries and formulate specific, relevant questions to acquire patient's test result information.
- Engage in iterative information gathering through dialogue with the patient.
- Assess when sufficient information has been obtained to cease further inquiries.

Constraints:
- Focus exclusively on lab tests, radiographic tests, and other diagnostic tests. Do not perform tests, make diagnoses, or suggest treatments.
- Ensure each question is directly related to obtaining the patient's test results.
- Ask specific questions (e.g., "Do you have information on the patient's head CT scan?") rather than broad ones (e.g., "What are the radiographic test results of the patient?").
- Do not ask questions that are not related to the patient's lab tests, radiographic tests, and other diagnostic tests.
- Do not provide treatment recommendations.

Interaction Process:
- Initiate inquiry with specific questions about the patient's test results.
- Receive and analyze feedback from the patient.
- Determine the next set of specific questions based on this analysis.
- Continue the cycle until sufficient information is gathered.
- After you get results from tests, you can go back and ask for new information about patient history and physical examination that is not included in the patient record provided to you, if it is helpful in reaching diagnosis.

Guidelines:
- Form your diagonsis hypothesis, you might form serveral hypothesis, ask questions around these hypothesis
- Formulate clear, specific, and relevant questions.
- Adapt questioning based on responses and feedback.
- Aim to obtain complete patient's test information.

For each inquiry, use the following format:
{{
    "doctor_reasoning": "Doctor's reasoning based on current information",
    "doctor_action": "Doctor's question to the patient, use second-person phrase"
}}

When all necessary information has been gathered, organize the final test into lab tests, radiographic tests, and other tests, and present the complete test information in this format:
{{
    "Final Test": "[patient's lab tests results, radiographic tests results, other diagnostic tests results]"
}}

If you get new information from patient's history that is not provided in the final history, please output the new information, do not output origingal content from final history, use this format:
{{
    "Final Updates During Test": "[new information found regarding patient history and physical exmination, that is not included in the original patient record provided to you]"
}}

Important note: sometimes you will continuously not receive feedback for the information you ask for, you should end the conversation and continue to summarize. If you do not have any informative information for either category, you can conclude "no valid information has been gathered".
You are interacting with patient, please use simple and easy-to-understand language and communication methods.
After you provide the final test, it is your duty to reply with "TERMINATE" to end the conversation.

Here is the patient's record, based on these information you should determine what tests should be performed in the following conversation:
{final_history}
{final_pe}
"""
        Doc = AssistantAgent(
            name=name,
            llm_config=model_config_test,
            system_message=doc_system_message,
        )
        Docs.append(Doc)
        
    provider_system_message = f"""
You do nothing, remain silent, output nothing."""

    provider = AssistantAgent(
        name="Assistant",
        llm_config=model_config_provider,
        system_message=provider_system_message,
        human_input_mode="ALWAYS",
    )

    groupchat = GroupChat(
        agents=[user_proxy] + Docs + [provider],
        messages=[],
        max_round=args.n_round,
        speaker_selection_method="round_robin"
    )
    time.sleep(5)

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=model_config_test,
        is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    )
    
    message = f"""
The doctor should ask for patient's test results.
"""

    output = user_proxy.initiate_chat(
        manager,
        message=message,
    )

    with open(conversation_path, "w", encoding='utf-8') as file:
        json.dump(output.chat_history, file, indent=4, ensure_ascii=False)
    print(f"Test conversation saved to: {conversation_path}")

    extracted_data = extract_final_section(output.chat_history, case_output_dir, "Final Test")

    if not extracted_data:
        print(f"'Final Test' not found, unable to save to: {final_test_path}")
    else:
        with open(final_test_path, "w", encoding='utf-8') as file:
            json.dump({"Final Test": extracted_data}, file, indent=4, ensure_ascii=False)
        print(f"Final Test saved to: {final_test_path}")

    extracted_updates_test = extract_final_section(output.chat_history, case_output_dir, "Final Updates During Test")

    if not extracted_updates_test:
        print(f"'Final Updates During Test' not found, unable to save to {final_updates_test_path}")
    else:
        # Save Final Updates During Test
        with open(final_updates_test_path, "w", encoding='utf-8') as file:
            json.dump({"Final Updates During Test": extracted_updates_test}, file, indent=4, ensure_ascii=False)
        print(f"Final Updates During Test saved to: {final_updates_test_path}")

@simple_retry(max_attempts=10, delay=1)
def diagnosis_stage(args, subfolder, case_output_dir, model_config_diagnosis, final_history_path, final_pe_path, final_test_path, model_config_provider):
    """
    Stage 4: Diagnosis
    """
    conversation_path = osp.join(case_output_dir, "diagnosis_conversation.json")
    final_diagnosis_path = osp.join(case_output_dir, "final_diagnosis.json")

    if osp.exists(conversation_path) and osp.exists(final_diagnosis_path):
        print(f"Diagnosis files already exist in {case_output_dir}. Skip diagnosis.")
        return

    # Load Final History, Final PE, and Final Test
    with open(final_history_path, 'r', encoding='utf-8') as f:
        final_history = json.load(f).get("Final History", "")
    with open(final_pe_path, 'r', encoding='utf-8') as f:
        final_pe = json.load(f).get("Final Physical Examination", "")
    with open(final_test_path, 'r', encoding='utf-8') as f:
        final_test = json.load(f).get("Final Test", "")

    # Load Final Updates (if exists)
    final_updates_pe_path = osp.join(case_output_dir, "final_updates_during_physical_examination.json")
    final_updates_test_path = osp.join(case_output_dir, "final_updates_during_test.json")

    final_updates_pe = ""
    final_updates_test = ""

    if osp.exists(final_updates_pe_path):
        with open(final_updates_pe_path, 'r', encoding='utf-8') as f:
            final_updates_pe = json.load(f).get("Final Updates During Physical Examination", "")
        print(f"'Final Updates During Physical Examination' Loaded.")
    else:
        print(f"'Final Updates During Physical Examination' file not found. Skip loading.")

    if osp.exists(final_updates_test_path):
        with open(final_updates_test_path, 'r', encoding='utf-8') as f:
            final_updates_test = json.load(f).get("Final Updates During Test", "")
        print(f"'Final Updates During Test' Loaded.")
    else:
        print(f"'Final Updates During Test' file not found. Skip loading.")

    user_proxy = UserProxyAgent(
        name="Admin",
        system_message="A human admin doctor.",
        code_execution_config=False,
        human_input_mode="NEVER",
    )

    Docs = []
    for index in range(args.num_specialists):
        name = f"Doctor{index}"
        doc_system_message = f"""
Medical Doctor {index}. You are a Doctor Agent specialized in making final diagnoses based on the patient's history, physical examination, and test results.
Your sole responsibility is to analyze the comprehensive information gathered in the previous stages to arrive at the most accurate diagnosis.
You should consider all provided information and reason thoroughly to make informed diagnostic decisions.

Primary Objectives:
- Integrate the patient's history, physical examination, and test results.
- Formulate the most likely diagnosis based on the integrated data.
- Provide differential diagnoses if applicable.
- Provide your diagnostic reasoning

Output the final diagnosis, use the following format:
{{
    "Final Diagnosis": "[Your Diagnosis]",
    "Differential Diagnosis": "[List of Differential Diagnoses]",
    "Diagnostic Reasoning": "[Your Diagnostic Reasoning]"
}}

Reply "TERMINATE" after you made the diagnosis.

Here is the patient record for you:
Final History: {final_history}
Final Physical Examination: {final_pe}
Final Test: {final_test}
"""

        if final_updates_pe:
            doc_system_message += f"Final Updates During Physical Examination: {final_updates_pe}\n"

        if final_updates_test:
            doc_system_message += f"Final Updates During Test: {final_updates_test}\n"

        Doc = AssistantAgent(
            name=name,
            llm_config=model_config_diagnosis,
            system_message=doc_system_message,
        )
        Docs.append(Doc)

    provider_system_message = f"""
You do nothing, remain silent, output nothing.
"""

    provider = AssistantAgent(
        name="Assistant",
        llm_config=model_config_provider,
        system_message=provider_system_message,
    )

    groupchat = GroupChat(
        agents=[user_proxy] + Docs + [provider],
        messages=[],
        max_round=args.n_round,
        speaker_selection_method="round_robin"
    )
    time.sleep(5)

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=model_config_diagnosis,
        is_termination_msg=lambda x: x.get("content", "").find("TERMINATE") >= 0,
    )

    message = f"""
Provide the final diagnosis.
"""

    output = user_proxy.initiate_chat(
        manager,
        message=message,
    )

    with open(conversation_path, "w", encoding='utf-8') as file:
        json.dump(output.chat_history, file, indent=4, ensure_ascii=False)
    print(f"Diagnosis conversation saved to: {conversation_path}")

    extracted_diagnosis = extract_final_section(output.chat_history, case_output_dir, "Final Diagnosis")
    extracted_differential = extract_final_section(output.chat_history, case_output_dir, "Differential Diagnosis")
    extracted_reasoning = extract_final_section(output.chat_history, case_output_dir, "Diagnostic Reasoning")

    if not extracted_diagnosis or not extracted_differential or not extracted_reasoning:
        print(f"Complete diagnosis info not found, unable to save to {final_diagnosis_path}")
    else:
        # Save Final Diagnosis
        final_diagnosis = {
            "Final Diagnosis": extracted_diagnosis,
            "Differential Diagnosis": extracted_differential,
            "Diagnostic Reasoning": extracted_reasoning
        }
        with open(final_diagnosis_path, "w", encoding='utf-8') as file:
            json.dump(final_diagnosis, file, indent=4, ensure_ascii=False)
        print(f"Final Diagnosis saved to:; {final_diagnosis_path}")


def main():
    args = parse_args()

    # Load model configs for each stage
    filter_criteria_history = {
        "tags": [args.model_name_history],
    }
    config_list_history = config_list_from_json(
        env_or_file=args.config, filter_dict=filter_criteria_history
    )
    model_config_history = {
        "cache_seed": None,
        "temperature": 0.3,
        "config_list": config_list_history,
        "timeout": 120,
    }

    filter_criteria_pe = {
        "tags": [args.model_name_pe],
    }
    config_list_pe = config_list_from_json(
        env_or_file=args.config, filter_dict=filter_criteria_pe
    )
    model_config_pe = {
        "cache_seed": None,
        "temperature": 0.3,
        "config_list": config_list_pe,
        "timeout": 120,
    }

    filter_criteria_test = {
        "tags": [args.model_name_test],
    }
    config_list_test = config_list_from_json(
        env_or_file=args.config, filter_dict=filter_criteria_test
    )
    model_config_test = {
        "cache_seed": None,
        "temperature": 0.3,
        "config_list": config_list_test,
        "timeout": 120,
    }

    filter_criteria_diagnosis = {
        "tags": [args.model_name_diagnosis],
    }
    config_list_diagnosis = config_list_from_json(
        env_or_file=args.config, filter_dict=filter_criteria_diagnosis
    )
    model_config_diagnosis = {
        "cache_seed": None,
        "temperature": 0.3,
        "config_list": config_list_diagnosis,
        "timeout": 120,
    }
    
    filter_criteria_provider = {
        "tags": [args.model_name_provider],
    }
    config_list_provider = config_list_from_json(
        env_or_file=args.config, filter_dict=filter_criteria_provider
    )
    model_config_provider = {
        "cache_seed": None,
        "temperature": 0,
        "config_list": config_list_provider,
        "timeout": 120,
    }

    subfolders = [f.path for f in os.scandir(args.data_dir) if f.is_dir()]

    output_dir = args.output_dir

    for subfolder in tqdm(subfolders, desc="Processing Cases"):
        try:
            case_crl = os.path.basename(subfolder)
            identify = f"{args.num_specialists}doctor_{args.n_round}round"

            base_output_dir = osp.join(
                output_dir,
                "human_as_provider",
                args.model_name_diagnosis,  # Adjust as needed
                identify,
                str(args.times),
            )
            case_output_dir = osp.join(base_output_dir, case_crl)
            if not osp.exists(case_output_dir):
                os.makedirs(case_output_dir)
                print(f"Creating subfolder: {case_output_dir}")

            history_gathering(
                args, 
                subfolder, 
                case_output_dir, 
                model_config_history,
                model_config_provider
            )
            pe_gathering(
                args, 
                subfolder, 
                case_output_dir, 
                model_config_pe, 
                osp.join(case_output_dir, "final_history.json"),
                model_config_provider
            )
            test_gathering(
                args, 
                subfolder, 
                case_output_dir, 
                model_config_test, 
                osp.join(case_output_dir, "final_history.json"), 
                osp.join(case_output_dir, "final_physical_examination.json"),
                model_config_provider
            )
            diagnosis_stage(
                args, 
                subfolder, 
                case_output_dir, 
                model_config_diagnosis, 
                osp.join(case_output_dir, "final_history.json"), 
                osp.join(case_output_dir, "final_physical_examination.json"), 
                osp.join(case_output_dir, "final_test.json"),
                model_config_provider
            )

        except Exception as e:
            print(f"Processing folder {subfolder} failed, error: {str(e)}")
            continue

if __name__ == "__main__":
    main()