# ### conda deactivate
# conda activate aenv
# python main_integrated.py
import os
import uuid
import string
from dotenv import load_dotenv
from langchain.document_loaders import CSVLoader
from langchain.indexes import VectorstoreIndexCreator
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler
import datetime
from threading import Thread
from queue import Queue
import sys
import sounddevice as sd
import soundfile as sf
import string
import asyncio
import nest_asyncio
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

nest_asyncio.apply()
from stream_text_to_audio import stream_text_to_audio

sys.path.append("./components")
from speech_to_text import transcribe_stream
from filler_mapping import classify_and_play_audio, refresh_learning_data

# Load environment variables
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PLAYHT_API_KEY = os.environ.get("PLAYHT_API_KEY")
PLAYHT_USER_ID = os.environ.get("PLAYHT_USER_ID")
CSV_FILE_PATH = os.environ.get("CSV_FILE_PATH")

os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
os.environ["PLAYHT_API_KEY"] = PLAYHT_API_KEY
os.environ["PLAYHT_USER_ID"] = PLAYHT_USER_ID

sys.path.append("./components")


class DictionaryCallback(BaseCallbackHandler):
    def __init__(self, q):
        self.q = q
        self.words_list = []
        self.loop = asyncio.new_event_loop()
        self.thread = Thread(target=self.start_loop, args=(self.loop,))
        self.thread.start()

        self.phrases_dict = {
            "That 's great to hear!": "Thatsgreattohear.wav",
            "The Google Pixel phones are an excellent choice.": "TheGooglePixelphonesareanexcellentchoice.wav",
            "They offer a fantastic camera experience and a pure Android operating system.": "TheyofferafantasticcameraexperienceandapureAndroidoperatingsystem.wav",
            "Is there anything specific you 're looking for in a smartphone?": "Isthereanythingspecificyourelookingforinasmartphone.wav",
            "Absolutely!": "Absolutely.wav",
            "Camera quality is one of the standout features of Google Pixel phones.": "CameraqualityisoneofthestandoutfeaturesofGooglePixelphones.wav",
            "They are known for their exceptional camera capabilities, especially in low -light conditions.": "Theyareknownfortheirexceptionalcameracapabilitiesespeciallyinlowlightconditions.wav",
            "The Google Pixel 6, in particular, comes with a 50 megapixel main camera and Google 's Night Sight technology, which ensures clear and vibrant photos even in challenging lighting situations.": "TheGooglePixel6inparticularcomeswitha50megapixelmaincameraandGooglesNightSighttechnologywhichensuresclearandvibrantphotoseveninchallenginglightingsituations.wav",
            "If camera quality is a top priority for you, the Google Pixel 6 would be an excellent choice.": "IfcameraqualityisatoppriorityforyoutheGooglePixel6wouldbeanexcellentchoice.wav",
            "Would you like to book an appointment to visit our showroom and experience the Google Pixel 6 firsthand?": "WouldyouliketobookanappointmenttovisitourshowroomandexperiencetheGooglePixel6firsthand.wav",
            "That 's great to hear!": "Thatsgreattohear.wav",
            "We have a wide range of Google Pixel phones available in our store.": "WehaveawiderangeofGooglePixelphonesavailableinourshowroom.wav",
            "When would you like to visit us?": "Whenwouldyouliketovisitus.wav",
            "Can I have your name and contact number to schedule an appointment for you?": "CanIhaveyournameandcontactnumbertoscheduleanappointmentforyou.wav",
            "Great, John!": "GreatJohn.wav",
            "Thank you for providing your name and contact number.": "Thankyouforprovidingyournameandcontactnumber.wav",
            "I have scheduled an appointment for you to visit our shop and experience the Google Pixel phones firsthand.": "IhavescheduledanappointmentforyoutovisitourshopandexperiencetheGooglePixelphonesfirsthand.wav",
            "Our team at Gadget Hub is excited to assist you in finding the perfect phone with excellent camera quality.": "OurteamatGadgetHubisexcitedtoassistyouinfindingtheperfectphonewithexcellentcameraquality.wav",
            "We look forward to seeing you soon!": "Welookforwardtoseeingyousoon.wav",
            "Have a great day!": "Haveagreatday.wav",
        }
        self.is_answer_finished = False
        self.timeout = 0.2  # Set your desired timeout value in seconds
        self.timer = None
        self.index = faiss.IndexFlatL2(embedding_size)  # Assuming embedding_size is the size of your embeddings
        self.add_phrases_to_index()
        self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
    
    def text_to_embedding(self, text):
        # Convert the text to an embedding (numpy array)
        embedding = self.model.encode([text])[0]
        return embedding
    
    def add_phrases_to_index(self):
        for phrase in self.phrases_dict.keys():
            embedding = self.text_to_embedding(phrase)
            self.index.add(np.array([embedding]))

    def start_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    async def play_audio_async(self, file_id):
        print("play_audio_async called")
        file_path = f"components/audio_files_pixel/{file_id}"
        if os.path.exists(file_path):
            data, samplerate = sf.read(file_path)
            sd.play(data, samplerate)
            sd.wait()
        else:
            print(f"Error: {file_path} does not exist")

    async def stream_audio_playht(self, text):
        print("stream_audio_playht called")
        # Use the stream_text_to_audio function to stream the text
        stream_text_to_audio(
            text, os.environ.get("PLAYHT_API_KEY"), os.environ.get("PLAYHT_USER_ID")
        )

    async def search_and_play_audio(self, combined_words):
        print("search_and_play_audio called")
        if self.is_answer_finished:  # Check whether the answer is finished or not
            print("Answer is finished. Not matching.")
            return
        audio_file_id = self.phrases_dict.get(combined_words)
        if audio_file_id:
            print(f"Match found in Dictionary for combined words: {combined_words}")
            # await self.play_audio_async(f"{audio_file_id}.mp3")
            await self.play_audio_async(f"{audio_file_id}")
            self.words_list.clear()
        else:
            print(f"No match found in Dictionary for combined words: {combined_words}")
            await self.stream_audio_playht(
                combined_words
            )  # Call PlayHT API when no match is found

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        if self.timer:
            self.timer.cancel()
        self.is_answer_finished = False
        self.q.put(token)
        stripped_token = token.strip()

        if not self.words_list:
            self.words_list.append(stripped_token)
        else:
            if stripped_token in string.punctuation:
                self.words_list.append(stripped_token)
            else:
                separator = " "
                self.words_list.append(separator + stripped_token)

        combined_words = "".join(self.words_list).strip()
        if stripped_token in [".", "!", "?"]:
            embedding = self.text_to_embedding(combined_words)
            D, I = self.index.search(np.array([embedding]), 1)  # Search the nearest embedding in the index
            if D[0][0] < threshold:  # Assuming threshold is a predefined threshold for similarity
                matched_phrase = list(self.phrases_dict.keys())[I[0][0]]
                audio_file_id = self.phrases_dict[matched_phrase]
                future = asyncio.run_coroutine_threadsafe(
                    self.play_audio_async(f"{audio_file_id}"), self.loop
                )
                future.result()
            else:
                future = asyncio.run_coroutine_threadsafe(
                    self.stream_audio_playht(combined_words), self.loop
                )
                future.result()

    def set_answer_finished(self):
        print("Timer expired. Setting is_answer_finished to True.")
        self.is_answer_finished = True

    def on_llm_end(self, *args, **kwargs) -> None:
        print("on_llm_end called")  # Debug print
        self.is_answer_finished = True
        self.words_list.clear()  # Clear the words_list when on_llm_end is called
        return self.q.empty()

    def stop_loop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


def generate_unique_id():
    return str(uuid.uuid4())


conversation_id = generate_unique_id()


def langchain_tasks(
    query, full_query, chain, start_time
):  # <-- Add start_time as an argument
    response = chain({"question": full_query})
    print(f"Response received: {response}")
    end_time = datetime.datetime.now()
    time_taken = (end_time - start_time).total_seconds()
    print(f"Time taken: {time_taken}")


def chat_with_user():
    refresh_learning_data()  # Call the method here to refresh learning data
    loader = CSVLoader(file_path=CSV_FILE_PATH)
    index_creator = VectorstoreIndexCreator()
    docsearch = index_creator.from_loaders([loader])

    q = Queue()
    job_done = object()
    llm = ChatOpenAI(
        streaming=True,
        callbacks=[DictionaryCallback(q)],  # Use the custom callback handler here
        temperature=0,
        openai_api_key=OPENAI_API_KEY,
    )
    chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=docsearch.vectorstore.as_retriever(),
        input_key="question",
    )

    opening_line = "Hello I'm Jenny from Gadget Hub. We noticed that you were looking for Google Pixel phone on our website. Are you interested in purchasing a new phone at the moment?"
    print(opening_line)
    data, fs = sf.read(f"components/audio_files_pixel/intro.wav", dtype="float32")
    sd.play(data, fs)
    sd.wait()

    chat_history = [("Response", opening_line)]
    sales_bot_statement = "You are a sales bot. Your main objective is to convince the user to buy a Google Pixel phone rather than Iphone. Begin the conversation by discussing what features they are looking for. If the user shows interest in buying or knowing more, encourage them to visit the shop to experience the product firsthand. Be attentive to user's reactions and responses. If the user seems interested or willing to visit the shop, politely ask for their name and contact number to book an appointment for them. Say something like 'Can I have your name and contact number to schedule an appointment for you to visit our shop?'. Ensure to be courteous and maintain a friendly tone throughout the conversation, addressing any inquiries or concerns the user may have to facilitate the sales process. When they give you the name and number, end the conversation by telling then to have a great day. You have been given the chat history. Give response in short to the last query only and continue the conversation accordingly. "

    try:
        while True:
            query = transcribe_stream()
            if query.lower() == "exit":
                break
            start_time = datetime.datetime.now()
            chat_history.append((query, ""))
            last_query = '"Query": "' + query + '"'
            context = ". ".join(
                [
                    "Query: " + entry[0] + ". Response: " + entry[1]
                    for entry in chat_history
                ]
            )
            full_query = sales_bot_statement + (
                context + ". " + last_query if context else last_query
            )
            # Create and start a new thread for Langchain tasks
            langchain_thread = Thread(
                target=langchain_tasks, args=(query, full_query, chain, start_time)
            )  # <-- Pass start_time
            langchain_thread.start()

            # Call classify_and_play_audio synchronously
            classify_and_play_audio(query)  # <-- Call the function
    finally:
        # Stop the event loop and join the thread when 'exit' is pressed
        llm.callbacks[0].stop_loop()
        llm.callbacks[0].thread.join()


if __name__ == "__main__":
    chat_history = chat_with_user()
