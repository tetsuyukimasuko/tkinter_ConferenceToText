from tkinter import*
import tkinter.ttk as ttk
import tkinter.filedialog as tkfd
import tkinter.messagebox as tkmsg

import pyaudio
from chardet import UniversalDetector

import wave
import time
import math
import numpy as np
import sys
import threading
import os
import shutil
import glob
import tempfile
import csv
import functools
import json
import re

from watson_developer_cloud import SpeechToTextV1

from PIL import Image, ImageTk, ImageDraw



# In[1]:ウィジェットハンドラ

#辞書登録用サブウィンドウ
sub_win_status_handler=None

#Setting Frame
device_list_handler=[]
speaker_list_handler=[]
detect_check_handler=[]
delete_button_handler=[]
scale_handler=[]
container_handler=[]
separator_handler=[]

#Operation Frame
status_label_handler=None

#Result Frame
treeview_handler=None

# In[2]:グローバル変数

#サブウィンドウ自身
sub_win = None

#チャンネル数
CH=0

#ワトソンを使用するためのドライバとカスタムモデルID
WSTT=None
ID=None

#辞書を使用するか否か
use_dict=None

#一時ファイルのパス
while True:
    try:
        FILEPATH=tempfile.mkdtemp()
        print(FILEPATH)
        break
    except:
        pass

# In[3]:クラス

#デバイスの認識関連
class AudioMethods():

    def check_encoding(self,binary):
        detector=UniversalDetector()
        detector.feed(binary)
        detector.close()
        return detector.result['encoding']

    def device_list(self):
        #デバイス表示
        CHUNK = 2048
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 44100

        mic_list=[]
        index_list=[]
        total_tuple=[]
    
        pa = pyaudio.PyAudio()
        for device_index in range(pa.get_device_count()):
            metadata = pa.get_device_info_by_index(device_index)
        
            try:
                encoding=self.check_encoding(metadata['name'])
                tmp=metadata['name'].decode(encoding)
                mic_list.append(str(device_index)+"_"+tmp)
                index_list.append(device_index)

            except:
                #ここの条件は変えよう
                if 'ƒ}ƒCƒN' in metadata['name']:
                    metadata['name']=metadata["name"].replace('ƒ}ƒCƒN','マイク')
                if '”z—ñ' in metadata['name']:
                    metadata['name']=metadata["name"].replace('”z—ñ','配列')
                mic_list.append(str(device_index)+"_"+metadata['name'])
                index_list.append(device_index)
        pa.terminate()

        for i in range(len(mic_list)):
            total_tuple.append(mic_list[i])
        total_tuple=tuple(total_tuple)
        return total_tuple

#マイク録音関連
class RecordMethods():
    def __init__(self):
        #スレッド終了処理。
        self.Thread_Stop=False

        #ポートのオープン処理
        self.port_opening=False

    def StartRecording(self, speakers, devices):
        global FILEPATH
        global status_label_handler
        
        self.Thread_Stop=False

        #全員分のフォルダ作成
        for sp in speakers:
            try:
                os.mkdir(os.path.join(FILEPATH,sp))
            except:
                pass

        #簡易発話区間認識+録音。ここをマルチスレッド化。
        threads=[]

        for i in range(len(speakers)):
            index=0
            for name in speaker_list_handler:
                if speakers[i]==name.get():
                    break
                else:
                    index+=1

            handler=detect_check_handler[index]
            slider_handler=scale_handler[index]

            thread=threading.Thread(target=self.VoiceDetection,args=(devices[i],speakers[i],handler,slider_handler,FILEPATH))
            threads.append(thread)
            #ポートが開くまで待つ
            self.port_opening=True
            status_label_handler.configure(text=speakers[i]+'準備中...')
            status_label_handler.update_idletasks()
            thread.start()
            while self.port_opening:
                if self.port_opening==False:
                    break
            
            thread=threading.Thread(target=self.SpeechToText,args=(FILEPATH,speakers[i]))
            threads.append(thread)
            thread.start()

        status_label_handler.configure(text='録音中...',foreground='red')
        
    def EndRecording(self):
        self.Thread_Stop=True
        
    def ConvertToDB(self,array):
        n=len(array)
    
        #二乗和
        tmp=np.square(array)
        sm=np.sum(tmp)

        #実効値。
        V=sm/n


        #デシベル。
        dB=20*math.log10(V)

        return dB

    def VoiceDetection(self,device,user_name,handler,slider_handler,FILEPATH):


        try:
        
            CHUNK = 2048
            FORMAT = pyaudio.paInt16
            CHANNELS = 1
            RATE = 16000

            while True:
                #pyaudio開始
                #ここがかぶると起動しない
                frames = []
                bufferframes=[]
                Stream_write=False
                Stream_end=False
                silent_sounter=0
                p = pyaudio.PyAudio()
                stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        input_device_index=device,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
                self.port_opening=False

                #発話区間認識。何かしゃべったら抜け出す
                while True:
 
                    data = stream.read(CHUNK)

                    #各フレームの振幅をとる。-0.1～0.1で正規化。
                    tmp_data=np.frombuffer(data, dtype="int16")/32768.0
            
                    #デシベル変換
                    dB=self.ConvertToDB(tmp_data)
                    pg_value=120+dB

                    handler.configure(value=pg_value)

                    #sys.stdout.write("\r%f"% dB)
                    #sys.stdout.flush()

                    #平均値が閾値以上であれば、Stream_writeをTrueにする。かつ、無音カウンターを0にする。
                    #閾値以下で、かつStream_writeが既にTrueだったら、カウンターを1つ足す。
                    #カウンターが7つ(0.9秒)たまったら、Stream_endをTrueにする
                    #ただし、発話途中で一時的に音量が下がっているだけだったら、無音カウンターは0に戻す。
                    #このときの閾値はDETECT_VOLUME-10[dB]とする。

                    DETECT_VOLUME=slider_handler.get()-120
                    #print(dB,DETECT_VOLUME)

                    if dB>DETECT_VOLUME:
                        Stream_write=True
                        silent_sounter=0
                    else:
                        if Stream_write:
                            if dB>DETECT_VOLUME-10:
                                silent_sounter=0
                            else:
                                silent_sounter+=1

                            if silent_sounter>7:
                                Stream_end=True

                    #stream_writeがfalseなら、バッファに追加。
                    #もしバッファが7つ(0.9秒)になっちゃったら先頭を削除する。
                    #もしtrueなら、framesに追加
                    if not Stream_write:
                        bufferframes.append(data)
                        if len(bufferframes)>7:
                            del bufferframes[0]
                    else:
                        frames.append(data)

                    if Stream_end:
                        frames=bufferframes+frames
                        break

                    if self.Thread_Stop:
                        break

                if self.Thread_Stop:
                    handler.configure(value=0)
                    break
        
                print('*done recording')
                stream.stop_stream()
                stream.close()
                p.terminate()
                tmp=b''.join(frames)
    
                #保存用wavをつくる
                filename=str(time.ctime())+"_"+user_name+'.wav'
                filename=filename.replace(':','-')
                filename=FILEPATH+'\\'+user_name+'\\'+filename

                wf = wave.open(filename, 'wb')
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(p.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(tmp)
                wf.close()

        except:
            import traceback
            traceback.print_exc()

    def SpeechToText(self,FILEPATH,speaker):
        global use_dict
        global treeview_handler
        if use_dict.get()==1:
            custom=True
        else:
            custom=False

        while True:
            filelist=glob.glob(FILEPATH+'\\'+speaker+'\\'+'*.wav')
            if len(filelist)>0:
                for file in filelist:
                    with open(file,'rb') as f:
                        try:
                            
                            tmp=file.replace(FILEPATH+'\\'+speaker+'\\','')
                            t=tmp.split('_')[0]
                            if custom:
                                txt=WSTT.RecognizeAudio(f,customization_id=ID)
                            else:
                                txt=WSTT.RecognizeAudio(f)
                            print(t.replace('-',':'),speaker,txt)
                            tmp=(t,speaker,txt)
                            if txt!='unrecognized':
                                treeview_handler.insert("","end",values=tmp)
                                self.treeview_sort_column(treeview_handler,1,False)


                        except:
                            pass
                    #でばぐ
                    os.remove(file)
            else:
                if self.Thread_Stop:                    
                    break

    #表のソート関数
    def treeview_sort_column(tv, col, reverse):
        l = [(tv.set(k, col), k) for k in tv.get_children('')]
        l.sort(reverse=reverse)

        # rearrange items in sorted positions
        for index, (val, k) in enumerate(l):
            tv.move(k, '', index)

#ワトソンを使いやすくするクラス
class WatsonSTT():
    #初期化処理で認証情報を入れる
    #TODO 今はチェンジのアカウントで一元管理してるけど、組織ごとに分ける？→組織ごとに分けるべき。認証情報を読み込ませてdb登録するべき。
    #TODO また、全員の発言を同時に処理するために、リクエストごとにセッションを作成すべき！Recognizeを改造すべし。
    def __init__(self,uname,password):
        self.user_name=uname
        self.url='https://stream.watsonplatform.net/speech-to-text/api'
        self.password=password
        self.speech_to_text=SpeechToTextV1(username=self.user_name,password=self.password,url=self.url)

    #カスタムモデルの作成を行う関数。
    def CreateCustomModel(self,model_name,model='ja'):
        
        #多言語対応
        if model=='ja':
            base_model='ja-JP_BroadbandModel'
        elif model=='en':
            base_model='en-US_BroadbandModel'       
        
        #リストアップ
        custom_models=self.speech_to_text.list_language_models()
        models=custom_models['customizations']


        custom_model=self.speech_to_text.create_language_model(model_name,base_model)
        return custom_model['customization_id']

    #カスタムモデルの削除
    def DeleteCustomModel(self,id):
        self.speech_to_text.delete_language_model(id)

    #カスタムモデルの単語を更新する関数
    #辞書を渡す。例 : {'部長' : ['ブチョウ','ブチョー'], '課長' : ['カチョウ','カチョー']}
    #既にある単語が指定された場合は、読み仮名が同じかどうかを調査し、違う場合は更新する。同じ場合は無視する。
    #渡した辞書にない単語は削除される。
    #TODO lockedのエラーが出たときにちゃんとエラーを出力する
    def AddCustomWords(self,model_id,dict):
        keys=list(dict.keys())
        word_list=self.speech_to_text.list_words(model_id)
        word_list=word_list['words']
        existing_word=[]
        existing_sound=[]
        new_word_input=False

        if len(word_list)>0:
            for i in range(len(word_list)):
                word_name=word_list[i]['word']
                word_sound=word_list[i]['sounds_like']
                existing_word.append(word_name)
                existing_sound.append(word_sound)

        for i in range(len(keys)):
            if keys[i] in existing_word:
                j=existing_word.index(keys[i])
                if set(dict[keys[i]])==set(existing_sound[j]):
                    print('単語',keys[i],'は登録済みです。')
                    sub_win_status_handler.configure(text='単語 '+keys[i]+' は登録済みです。')
                    sub_win_status_handler.update_idletasks()
                else:
                    print('単語',keys[i],'は登録済みですが、読み仮名を更新します。')
                    sub_win_status_handler.configure(text='単語 '+keys[i]+' は登録済みですが、読み仮名を更新します。')
                    sub_win_status_handler.update_idletasks()
                    self.speech_to_text.delete_word(model_id,keys[i])
                    sound=dict[keys[i]]
                    self.speech_to_text.add_word(model_id,keys[i],sound)
                    new_word_input=True
                existing_word.remove(keys[i])
                existing_sound.remove(existing_sound[j])
            else:
                sound=dict[keys[i]]
                print('単語',keys[i],'を新規登録します。')
                sub_win_status_handler.configure(text='単語 '+keys[i]+' を新規登録します。')
                sub_win_status_handler.update_idletasks()
                self.speech_to_text.add_word(model_id,keys[i],sound)
                new_word_input=True
        

        #渡さなかった単語の削除
        deleted_word=[]
        sub_win_status_handler.configure(text='その他の単語を削除します。')
        sub_win_status_handler.update_idletasks()
        for tmp in existing_word:
            print('単語',tmp,'を削除します。')
            new_word_input=True
            deleted_word.append(tmp)

        if len(deleted_word)>0:    
            self.DeleteCustomWords(model_id,deleted_word)

        sub_win_status_handler.configure(text='言語モデルのトレーニング中...')
        sub_win_status_handler.update_idletasks()
        #トレーニング
        if new_word_input:
            tr=self.speech_to_text.train_language_model(model_id)

        #登録済み単語リスト出力
        word_list=self.speech_to_text.list_words(model_id)
        word_list=word_list['words']
        results={}
        if len(word_list)>0:
            for i in range(len(word_list)):
                word_name=word_list[i]['word']
                word_sound=word_list[i]['sounds_like']
                results.setdefault(word_name,word_sound)
        return results

    #登録されている単語をゲットする関数
    def GetCustomWords(self,model_id):
        #登録済み単語リスト出力
        word_list=self.speech_to_text.list_words(model_id)
        word_list=word_list['words']
        results={}
        if len(word_list)>0:
            for i in range(len(word_list)):
                word_name=word_list[i]['word']
                word_sound=word_list[i]['sounds_like']
                results.setdefault(word_name,word_sound)
        return results


    #カスタムモデルのidを全部持ってくる
    def ListCustomModels(self):
        results=[]
        custom_models=self.speech_to_text.list_language_models()
        models=custom_models['customizations']
        if len(models)>0:
            for i in range(len(models)):
                results.append(models[i]['customization_id'])
        return results


    #指定した名前のカスタムモデルのidを持ってくる
    def GetCustomModelByName(self,name):
        result=''
        custom_models=self.speech_to_text.list_language_models()
        models=custom_models['customizations']
        if len(models)>0:
            for i in range(len(models)):
                tmp=models[i]['name']
                if tmp==name:
                    result=models[i]['customization_id']
        return result



    #単語を削除する。wordsはlist
    def DeleteCustomWords(self,model_id,words):
        word_list=self.speech_to_text.list_words(model_id)
        word_list=word_list['words']

        existing_word=[]

        if len(word_list)>0:
            for i in range(len(word_list)):
                word_name=word_list[i]['word']
                existing_word.append(word_name)

        for word in words:
            if word in existing_word:
                #print(word,'を削除します。')
                self.speech_to_text.delete_word(model_id,word)
            else:
                #print(word,'なんて単語はありませんよ。')
                pass

    #音声認識を行う。セッションレス。
    def RecognizeAudio(self,file,delete_interjection=True,customization_id=None,customization_weight=0.3,model='ja'):

        #多言語対応
        if model=='ja':
            base_model='ja-JP_BroadbandModel'
        elif model=='en':
            base_model='en-US_BroadbandModel'

        #with open(file,'rb') as audio_file:
        audio_file=file
        try:
            if customization_id==None:
                r=self.speech_to_text.recognize(
                            audio=audio_file,
                            content_type='audio/wav',
                            timestamps=True,
                            word_confidence=True,
                            model=base_model
                            )
            else:
                model_info=self.speech_to_text.get_language_model(customization_id)
                base_model=model_info['base_model_name']
                while True:
                    model_info=self.speech_to_text.get_language_model(customization_id)
                    stat=model_info['status']
                    if stat=='available':
                        break
                r=self.speech_to_text.recognize(
                            audio=audio_file,
                            content_type='audio/wav',
                            timestamps=True,
                            word_confidence=True,
                            model=base_model,
                            customization_id=customization_id,
                            customization_weight=customization_weight
                            )

            tmp=r['results']

        except:
            tmp=[]

        transcripts=''

        if len(tmp)>0:
            for i in range(len(tmp)):
                #timestampに分ける
                results=r['results'][i]['alternatives'][0]['timestamps']
                tmp_result=''
                for result in results:
                    tmp_text=result[0]

                    #あいづちを除く
                    if delete_interjection:
                        mo=re.findall(r'D_\w+',tmp_text)
                        if len(mo)>0:
                            pass
                        else:
                            tmp_result+=tmp_text
                    else:
                        tmp_result+=tmp_text

                transcripts+=tmp_result.replace(' ','')

                #句読点を足す
                if model=='ja':
                    transcripts+='。'
                elif model=='en':
                    transcripts+='.'


        if transcripts=='':
            transcripts='unrecognized'

        transcripts=self.kansuji2arabic(transcripts,sep=True)

        return transcripts

    #漢数字をアラビア数字に変換
    #https://qiita.com/dosec/items/c6aef40fae6977fd89ab
    def kansuji2arabic(self,kstring, sep=False):
        
        tt_ksuji = str.maketrans('一二三四五六七八九〇', '1234567890')

        re_suji = re.compile(r'[十拾百千万億兆\d]+')
        re_kunit = re.compile(r'[十拾百千]|\d+')
        re_manshin = re.compile(r'[万億兆]|[^万億兆]+')

        TRANSUNIT = {'十': 10,
                     '百': 100,
                     '千': 1000}
        TRANSMANS = {'万': 10000,
                     '億': 100000000,
                     '兆': 1000000000000}

        def _transvalue(sj, re_obj=re_kunit, transdic=TRANSUNIT):
            unit = 1
            result = 0
            for piece in reversed(re_obj.findall(sj)):
                if piece in transdic:
                    if unit > 1:
                        result += unit
                    unit = transdic[piece]
                else:
                    val = int(piece) if piece.isdecimal() else _transvalue(piece)
                    result += val * unit
                    unit = 1

            if unit > 1:
                result += unit

            return result

        transuji = kstring.translate(tt_ksuji)
        for suji in sorted(set(re_suji.findall(transuji)), key=lambda s: len(s),
                               reverse=True):
            if not suji.isdecimal():
                arabic = _transvalue(suji, re_manshin, TRANSMANS)
                arabic = '{:,}'.format(arabic) if sep else str(arabic)
                transuji = transuji.replace(suji, arabic)

        return transuji

    #セッションを使う。非同期通信に需要はないかもしれないが一応。
    def RecognizeAudioWithSession(self,file,delete_interjection=False,customization_id=None,customization_weight=0.3,model='ja'):
        
         #多言語対応
        if model=='ja':
            base_model='ja-JP_BroadbandModel'
        elif model=='en':
            base_model='en-US_BroadbandModel'       
        
        #ここは送信形式でかえる
        with open(file, 'rb') as audio_file:
            if customization_id==None:
                r=self.speech_to_text.create_job(audio_file,'audio/wav',model=base_model,timestamps=True)
            else:
                model_info=self.speech_to_text.get_language_model(customization_id)
                base_model=model_info['base_model_name']
                while True:
                    model_info=self.speech_to_text.get_language_model(customization_id)
                    stat=model_info['status']
                    if stat=='available':
                        break
                r=self.speech_to_text.create_job(audio_file,'audio/wav',model='ja-JP_BroadbandModel',timestamps=True,customization_id=customization_id, customization_weight=customization_weight)

        job_id=r['id']

        while True:
            result=self.speech_to_text.check_job(job_id)
            stat=result['status']
            if stat=='completed':
                self.speech_to_text.delete_job(job_id)
                break

        count=len(result['results'])
        transcripts=''

        for i in range(count):

            results_len=len(result['results'][i]['results'])
            
            for j in range(results_len):
                
                #この中にalternativeがある。
                alternatives=result['results'][i]['results'][j]['alternatives']

                #今回は、最もconfidenceが高い、0番目のみを持ってくる。
                timestamps=alternatives[0]['timestamps']

                tmp_result=''

                for t in timestamps:
                    if delete_interjection:
                        mo=re.findall(r'D_\w+',t[0])
                        if len(mo)==0:
                            tmp_result+=t[0]
                    else:
                        tmp_result+=t[0]

                tmp_result=tmp_result.replace(' ','')
                transcripts+=tmp_result

                #まだ回りきっていなければ、発言と発言の間に空白を入れる
                if j<results_len-1:
                    transcripts+=' '      
        
        if transcripts=='':
            transcripts='unrecognized'

        transcripts=self.kansuji2arabic(transcripts,sep=True)

        return transcripts

#アカウント処理ウィンドウのクラス
class AccountManagement():

    def __init__(self):

        #ウィンドウを出して、IDとパスワードを入力させる
        self.Account_Window=Toplevel()
        self.Account_Window.title('アカウントの設定')
        self.Account_Window.resizable(0,0)
        self.Account_Window.grab_set()
        self.info_label=ttk.Label(self.Account_Window,text='IBM Watson Speech to Text のService credentials情報を入力してください(初回のみ必要)。')
        self.url_label=ttk.Label(self.Account_Window,text='https://console.bluemix.net/docs/services/speech-to-text/getting-started.html#gettingStarted')
        self.info_label.grid(row=0,column=0)
        self.url_label.grid(row=1,column=0)

        self.account_frame=ttk.LabelFrame(self.Account_Window,text='Service Credentials')
        self.account_frame.grid(row=2,column=0)

        self.username_label=ttk.Label(self.account_frame,text='username')
        self.password_label=ttk.Label(self.account_frame,text='password')
        self.username_input=ttk.Entry(self.account_frame,width=30)
        self.password_input=ttk.Entry(self.account_frame,show='*',width=30)

        self.username_label.grid(row=0,column=0)
        self.password_label.grid(row=1,column=0)
        self.username_input.grid(row=0,column=1)
        self.password_input.grid(row=1,column=1)

        self.submit_button=ttk.Button(self.Account_Window,text='submit',command=self.Submit)
        self.submit_button.grid(row=3,column=0,sticky=E)

        self.Account_Window.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.Account_Window.mainloop()

    def Submit(self):
        global WSTT
        global ID
        uname=self.username_input.get()
        password=self.password_input.get()
        WSTT=WatsonSTT(uname,password)
        try:
            l=WSTT.ListCustomModels()
            a=tkmsg.showinfo('アカウント確認','アカウント情報が確認されました。')
            self.Account_Window.destroy()
            #json保存
            dict={"username" : uname, "password" : password}
            with open('credentials.json','w',encoding='utf_8_sig') as f:
                json.dump(dict,f)
            ID=WSTT.GetCustomModelByName('tkinter')
            if ID=='':
                ID=WSTT.CreateCustomModel('tkinter')

        except:
            a=tkmsg.showwarning('アカウントエラー','アカウント情報が確認できませんでした。')

    def on_closing(self):
        sys.exit(0)

#辞書登録ウィンドウのクラス
class DictOp():

    
    word_add_window=None
    katakana = "ーァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペホボポマミムメモャヤュユョヨラリルレロヮワヰヱヲンヴ"

    def ViewDict(self):
        global sub_win
        global sub_win_status_handler
        global ID
        if sub_win is None or not sub_win.winfo_exists():
            sub_win = Toplevel()
            sub_win.title('辞書の編集')

            #メニュー
            menubar=Menu(sub_win)

            #file
            filemenu=Menu(menubar,tearoff=0)
            filemenu.add_command(label='CSVインポート',command=self.ImportCSV)

            #追加
            menubar.add_cascade(label='ファイル', menu=filemenu)

            #表示
            sub_win.config(menu=menubar)
            sub_win.resizable(0,0)

            sub_win.grab_set()

            #新規単語登録フレーム
            self.new_word_frame=ttk.LabelFrame(sub_win,text='新規単語登録')
            self.new_word_frame.grid(row=0,column=0,sticky=(E,W,S,N))

            #ラベル
            self.sub_label_1=ttk.Label(self.new_word_frame,text='単語')
            self.sub_label_1.grid(row=0,column=0)
            self.sub_label_2=ttk.Label(self.new_word_frame,text='ヨミガナ')
            self.sub_label_2.grid(row=0,column=1)

            #エントリー
            self.word_entry=ttk.Entry(self.new_word_frame,width=20)
            self.word_entry.grid(row=1,column=0)
            self.sound_entry=ttk.Entry(self.new_word_frame,width=20)
            self.sound_entry.grid(row=1,column=1)

            #ボタン
            self.add_single_word_btn=ttk.Button(self.new_word_frame,text='単語を追加',command=self.AddSingleWord)
            self.add_single_word_btn.grid(row=2,column=2)

            #単語参照フレーム
            self.dict_frame=ttk.LabelFrame(sub_win,text='登録単語一覧(登録済 : 黒　未登録 : 青)')
            self.dict_frame.grid(row=1,column=0,sticky=(E,W,S,N))

            #treeview
            ##Result Frame
            self.dict_table=ttk.Treeview(self.dict_frame,height=20)
            self.dict_table["columns"]=(1,2)
            self.dict_table["show"]="headings"
            self.dict_table.column(1,width=200)
            self.dict_table.column(2,width=200)
            self.dict_table.heading(1,text="単語")
            self.dict_table.heading(2,text="ヨミガナ")

            self.dict_table.grid(row=0,column=0,sticky=(E,W,S,N))

            #スクロールバー
            vsb=ttk.Scrollbar(self.dict_frame, orient="vertical", command=self.dict_table.yview)
            self.dict_table.configure(yscrollcommand=vsb.set)
            vsb.grid(row=0,column=1,sticky=(N,S))

            sub_win.columnconfigure(0,weight=1)
            sub_win.rowconfigure(0,weight=1)

            #オペレーションフレーム
            self.operate_frame=ttk.LabelFrame(sub_win,text='辞書の更新')
            self.operate_frame.grid(row=2,column=0,sticky=(E,W,S,N))

            #単語アップデートボタン
            self.push_btn=ttk.Button(self.operate_frame,text='辞書アップデート',command=self.UpdateDict,state='disable')
            self.push_btn.grid(row=0,column=0,sticky=(E,S,N))

            #ステータスバー
            self.statusbar=ttk.Label(self.operate_frame,text='')
            self.statusbar.grid(row=0,column=1,sticky=(W,S))
            sub_win_status_handler=self.statusbar

            #登録単語確認
            r=WSTT.GetCustomWords(ID)
            if len(r)>0:
                for word in r:
                    sound=r[word]
                    tmp=(word,sound)
                    self.dict_table.insert("","end",values=tmp)

    def AddSingleWord(self):
        word=self.word_entry.get()
        sound=self.sound_entry.get()

        word=word.replace(' ','_')
        word=word.replace('　','_')
        
        tmp=(word,sound)

        if word!='' and sound!='':
            if all([ch in self.katakana for ch in sound]):
                self.dict_table.insert("","end",values=tmp,tag='new')
                self.word_entry.delete(0, 'end')
                self.sound_entry.delete(0, 'end')
                self.push_btn.configure(state='enable')
                self.dict_table.tag_configure('new',background="#CCFFFF")
            else:
                a=tkmsg.showwarning('単語登録エラー','よみがなは全角カタカナで登録してください。')
        else:
            a=tkmsg.showwarning('単語登録エラー','空欄があります。')


    def UpdateDict(self):
        self.statusbar.configure(text='単語を登録しています...')
        self.statusbar.update_idletasks()
        dict={}
        for i in self.dict_table.get_children():
            tmp=self.dict_table.item(i)["values"]
            word=tmp[0]
            sound=tmp[1]
            dict.setdefault(word,[sound])

        r=WSTT.AddCustomWords(ID, dict)
        self.push_btn.configure(state='disable')
        self.statusbar.configure(text='')

        for i in self.dict_table.get_children():
            #print(self.dict_table.item(i)["values"])
            self.dict_table.delete(i)

        if len(r)>0:
            for word in r:
                sound=r[word]
                tmp=(word,sound)
                self.dict_table.insert("","end",values=tmp)        

    def ImportCSV(self):
        error=False
        fTyp=[('CSVファイル','*.csv')]
        cwd=os.getcwd()
        input=tkfd.askopenfilename(filetypes=fTyp,initialdir=cwd)

        if self.is_utf8_file_with_bom(input):
            encoding='utf_8_sig'
        else:
            encoding='utf_8'

        for i in self.dict_table.get_children():
            #print(self.dict_table.item(i)["values"])
            self.dict_table.delete(i)

        with open(input,'r',encoding=encoding) as f:
            reader=csv.reader(f)
            for row in reader:
                row[0]=row[0].replace(' ','_')
                row[0]=row[0].replace('　','_')
                tmp=(row[0],row[1])
                if all([ch in self.katakana for ch in row[1]]):
                    self.dict_table.insert("","end",values=tmp,tag='new')
                else:
                    error=True


        self.dict_table.tag_configure('new',background="#CCFFFF")
        self.push_btn.configure(state='enable')
        if error:
            a=tkmsg.showwarning('単語登録エラー','カタカナではないよみがなが設定されていた単語がありました。')

    def is_utf8_file_with_bom(self,filename):
        #utf-8 ファイルが BOM ありかどうかを判定する
        line_first = open(filename, encoding='utf-8').readline()
        return (line_first[0] == '\ufeff')

#メインウィンドウのクラス
class MainWindow():

    def __init__(self):

        global use_dict
        global ID
        global WSTT
        global status_label_handler
        global treeview_handler

        self.rm=RecordMethods()
        

        self.root = Tk()
        self.root.title('Main Window')
        self.root.rowconfigure(2, weight=1)
        self.root.columnconfigure(0,weight=1)

        #Treeviewのスタイル変更
        self.style=ttk.Style()
        # Treeviewの全部
        self.style.configure("Treeview",font=("",12))
        # TreeviewのHeading部分のみ
        self.style.configure("Treeview.Heading",font=("",14))

        ##フレーム群の定義
        
        #Setting Frame
        self.setting_frame=ttk.LabelFrame(self.root,relief='groove',text='Setting')
        self.setting_frame.grid(row=0, column=0,sticky=(W,S,N))

        #Operation Frame
        self.operation_frame=ttk.LabelFrame(self.root,relief='groove',text='Operation')
        self.operation_frame.grid(row=1, column=0,sticky=(W,S,N))

        #Result Frame
        self.result_frame=ttk.LabelFrame(self.root,relief='groove',text='Result')
        self.result_frame.grid(row=2, column=0,sticky=(E,W,S,N))

        ###各フレーム上のwidget群

        ##Setting Frame

        #ラベル群
        self.device_label=ttk.Label(self.setting_frame,width=30,text='使用マイク')
        self.speaker_label=ttk.Label(self.setting_frame,width=30,text='話者名')
        self.detect_label=ttk.Label(self.setting_frame,width=30,text='音量')
        self.channel_label=ttk.Label(self.setting_frame,width=20,text='チャンネル操作')

        self.device_label.grid(row=0,column=0)
        self.speaker_label.grid(row=0,column=1)
        self.detect_label.grid(row=0,column=2)
        self.channel_label.grid(row=0,column=3)

        #ボタン(初期段階ではCH追加ボタンだけ。各CHのボタンはAddCH関数で追加する。)
        self.ch_add_btn=ttk.Button(self.setting_frame,text='CH追加',command=self.AddChannel)
        self.ch_add_btn.grid(row=1,column=3)

        ##Operation Frame

        #録音ボタン描画
        size=40
        im=Image.new('RGB',(size,size),(256,256,256))
        draw = ImageDraw.Draw(im)
        draw.rectangle((0,0,size-1,size-1), fill=(216, 216, 216), outline=(0,0,0))
        draw.ellipse((5,5,size-5,size-5),fill=(255, 0, 0), outline=(0, 0, 0))
        rec_img = ImageTk.PhotoImage(im)
        self.start_btn=ttk.Button(self.operation_frame,image=rec_img,command=self.StartRecording)
        self.start_btn.grid(row=0,column=0)

        #停止ボタン描画
        im=Image.new('RGB',(size,size),(256,256,256))
        draw = ImageDraw.Draw(im)
        draw.rectangle((0,0,size-1,size-1), fill=(216, 216, 216), outline=(0,0,0))
        draw.rectangle((9,9,size-9,size-9), fill=(0, 0, 0), outline=(0,0,0))
        stp_img = ImageTk.PhotoImage(im)
        self.stop_btn=ttk.Button(self.operation_frame,image=stp_img,state='disabled',command=self.StopRecording)
        self.stop_btn.grid(row=0,column=1)

        #辞書使用チェックボタン描画
        use_dict=IntVar()
        self.check=ttk.Checkbutton(self.operation_frame,text='辞書を使用する', variable=use_dict)
        self.check.grid(row=0,column=2)

        #ステータスラベル描画
        self.status_label=ttk.Label(self.operation_frame, width=40,text='待機中',font=("",14))
        self.status_label.grid(row=0,column=3)
        status_label_handler=self.status_label

        ##Result Frame
        self.result_table=ttk.Treeview(self.result_frame,height=20)
        self.result_table["columns"]=(1,2,3)
        self.result_table["show"]="headings"
        self.result_table.column(1,width=100)
        self.result_table.column(2,width=100)
        self.result_table.column(3,width=600)
        self.result_table.heading(1,text="発話時刻")
        self.result_table.heading(2,text="話者")
        self.result_table.heading(3,text="発言")

        self.result_table.grid(row=0,column=0,sticky=(E,W,S,N))

        treeview_handler=self.result_table

        #スクロールバー
        self.vsb=ttk.Scrollbar(self.result_frame, orient="vertical", command=self.result_table.yview)
        self.result_table.configure(yscrollcommand=self.vsb.set)
        self.vsb.grid(row=0,column=1,sticky=(N,S))

        self.result_frame.columnconfigure(0,weight=1)
        self.result_frame.rowconfigure(0,weight=1)

        #メニュー
        self.menubar=Menu(self.root)

        #file
        self.filemenu=Menu(self.menubar,tearoff=0)
        self.filemenu.add_command(label='CSVエクスポート', command=self.Export)
        self.filemenu.add_separator()
        self.filemenu.add_command(label='終了', command=self.quit)

        #dict
        self.dictmenu=Menu(self.menubar,tearoff=0)
        self.dp=DictOp()
        self.dictmenu.add_command(label='辞書の編集',command=self.dp.ViewDict)

        #追加
        self.menubar.add_cascade(label='ファイル', menu=self.filemenu)
        self.menubar.add_cascade(label='辞書', menu=self.dictmenu)

        #表示
        self.root.config(menu=self.menubar)
    
        #クレデンシャルを読み込む。
        try:
            with open('credentials.json','r',encoding='utf_8_sig') as f:
                s=f.read()
                d=json.loads(s)
                uname=d['username']
                password=d['password']
                WSTT=WatsonSTT(uname,password)
                l=WSTT.ListCustomModels()
                a=tkmsg.showinfo('アカウント確認','アカウント情報が確認されました。')
                ID=WSTT.GetCustomModelByName('tkinter')
                if ID=='':
                    ID=WSTT.CreateCustomModel('tkinter')
        except:
            a=tkmsg.showwarning('アカウントエラー','アカウント情報が確認できませんでした。')
            account_input=AccountManagement()

        self.root.mainloop()

    #setting frame上のwidgetを一括off
    def ChangeAvailability(self,mode):

        global device_list_handler
        global speaker_list_handler
        global delete_button_handler

        for i in range(CH):
            device_list_handler[i].configure(state=mode)
            speaker_list_handler[i].configure(state=mode)
            delete_button_handler[i].configure(state=mode)
        self.ch_add_btn.configure(state=mode)
        self.check.configure(state=mode)
        if mode=='enable':
            self.menubar.entryconfig("ファイル", state='normal')
            self.menubar.entryconfig("辞書", state='normal')
        elif mode=='disable':
            self.menubar.entryconfig("ファイル", state=mode)
            self.menubar.entryconfig("辞書", state=mode)

    #録音スタート
    def StartRecording(self):

        global device_list_handler
        global speaker_list_handler

        if CH>0:
            device_list=[int(device_list_handler[i].get()[0]) for i in range(CH)]
            speaker_list=[speaker_list_handler[i].get() for i in range(CH)]

            if '' in list(set(speaker_list)):
                self.status_label.configure(text='話者名に空欄があります。',foreground='red')
                self.status_label.update_idletasks()
                time.sleep(0.5)
                self.status_label.configure(text='待機中',foreground='black')
            elif len(list(set(device_list)))!=len(device_list):
                self.status_label.configure(text='デバイスが重複しています。',foreground='red')
                self.status_label.update_idletasks()
                time.sleep(0.5)
                self.status_labelconfigure(text='待機中',foreground='black')
            elif len(list(set(speaker_list)))!=len(speaker_list):
                self.status_label.configure(text='話者名が重複しています。',foreground='red')
                self.status_label.update_idletasks()
                time.sleep(0.5)
                self.status_label.configure(text='待機中',foreground='black')
            else:
                self.start_btn.configure(state='disable')
                self.stop_btn.configure(state='enable')
                self.ChangeAvailability('disable')
                self.rm.StartRecording(speaker_list,device_list)
        else:
            self.status_label.configure(text='チャンネル数が0です。',foreground='red')
            self.status_label.update_idletasks()
            time.sleep(0.5)
            self.status_label.configure(text='待機中',foreground='black')

    #録音ストップ
    def StopRecording(self):
        self.start_btn.configure(state='enable')
        self.stop_btn.configure(state='disable')
        self.ChangeAvailability('enable')
        self.rm.EndRecording()
        self.status_label.configure(text='待機中',foreground='black')

    #チャンネル追加
    def AddChannel(self):

        global CH
        global device_list_handler
        global speaker_list_handler
        global detect_check_handler
        global delete_button_handler
        global scale_handler
        global container_handler
        global separator_handler
        
        am=AudioMethods()

        device_list_values=[]
        speaker_list_values=[]
        self.ch_add_btn.destroy()

        #格納済みの値を保管
        if CH>0:

            for i in range(CH):
                device_list_values.append(int(device_list_handler[i].get()[0]))
                speaker_list_values.append(speaker_list_handler[i].get())

            #既に配置されているコンボボックスとエントリー、音量バーとスケール、フレーム、セパレーター、チャンネル削除ボタンを削除
            for i in range(CH):
                device_list_handler[i].destroy()
                speaker_list_handler[i].destroy()
                detect_check_handler[i].destroy()
                delete_button_handler[i].destroy()
                scale_handler[i].destroy()
                container_handler[i].destroy()
                separator_handler[i].destroy()
                

        #配列を空にする
        device_list_handler=[]
        speaker_list_handler=[]
        detect_check_handler=[]
        delete_button_handler=[]
        scale_handler=[]
        container_handler=[]
        separator_handler=[]

        #配列の値を増やす
        device_list_values.append(0)
        speaker_list_values.append("")
        
        #チャンネル増やす
        CH+=1
        list=am.device_list()

        #ループする。ここを高速化できないだろうか、、、
        for i in range(CH):
        
            #デバイスリスト
            tmp_device_list=ttk.Combobox(self.setting_frame,state='readonly', width=25)
            tmp_device_list["values"]=list
            tmp_device_list.current(device_list_values[i])
            tmp_device_list.grid(row=2*i+1, column=0,sticky=W)

            #スピーカーリスト
            tmp_speaker_list=ttk.Entry(self.setting_frame,width=25)
            tmp_speaker_list.insert(0,speaker_list_values[i])
            tmp_speaker_list.grid(row=2*i+1, column=1,sticky=W)

            #音量とスケールを置くためのフレーム
            tmp_frame=ttk.Frame(self.setting_frame)
            tmp_frame.grid(row=2*i+1, column=2)

            #音量バー
            tmp_detect_check=ttk.Progressbar(tmp_frame,length=240,orient=HORIZONTAL,mode='determinate',maximum=120)
            tmp_detect_check.grid(row=0, column=0)

            #音量バーの下にスケールを置く
            tmp_scale=ttk.Scale(tmp_frame,from_=0,to=120,orient=HORIZONTAL,length=240)
            tmp_scale.set(60)
            tmp_scale.grid(row=1, column=0)

            #削除ボタン
            tmp_del_button=ttk.Button(self.setting_frame,text='削除',command=functools.partial(self.DelChannel,i))
            tmp_del_button.grid(row=2*i+1, column=3)

            #セパレータ
            tmp_separator=ttk.Separator(self.setting_frame, orient="horizontal")
            tmp_separator.grid(row=2*i+2, columnspan=4, sticky=(W,E))

            #ハンドラに値追加
            device_list_handler.append(tmp_device_list)
            speaker_list_handler.append(tmp_speaker_list)
            detect_check_handler.append(tmp_detect_check)
            delete_button_handler.append(tmp_del_button)
            scale_handler.append(tmp_scale)
            container_handler.append(tmp_frame)
            separator_handler.append(tmp_separator)
        else:
            #追加ボタン
            self.ch_add_btn=ttk.Button(self.setting_frame,text='CH追加',command=self.AddChannel)
            self.ch_add_btn.grid(row=2*CH+1,column=3)

    #チャンネル削除
    def DelChannel(self,index):

        global CH
        global device_list_handler
        global speaker_list_handler
        global detect_check_handler
        global delete_button_handler
        global scale_handler
        global container_handler
        global separator_handler
        
        am=AudioMethods()

        device_list_values=[]
        speaker_list_values=[]
        self.ch_add_btn.destroy()

        #格納済みの値を保管
        if CH>0:

            for i in range(CH):
                device_list_values.append(int(device_list_handler[i].get()[0]))
                speaker_list_values.append(speaker_list_handler[i].get())

            #既に配置されているコンボボックスとエントリー、検出ラベル、チャンネル削除ボタンを削除
            for i in range(CH):
                device_list_handler[i].destroy()
                speaker_list_handler[i].destroy()
                detect_check_handler[i].destroy()
                delete_button_handler[i].destroy()
                scale_handler[i].destroy()
                container_handler[i].destroy()
                separator_handler[i].destroy()

        #配列を空にする
        device_list_handler=[]
        speaker_list_handler=[]
        detect_check_handler=[]
        delete_button_handler=[]
        scale_handler=[]
        container_handler=[]
        separator_handler=[]
        
        #チャンネル減らす
        CH-=1
        list=am.device_list()

        #指定したindexの値を削除する
        device_list_values.pop(index)
        speaker_list_values.pop(index)

        #ループする。ここを高速化できないだろうか、、、
        for i in range(CH):

            #デバイスリスト
            tmp_device_list=ttk.Combobox(self.setting_frame,state='readonly', width=25)
            tmp_device_list["values"]=list
            tmp_device_list.current(device_list_values[i])
            tmp_device_list.grid(row=2*i+1, column=0,sticky=W)

            #スピーカーリスト
            tmp_speaker_list=ttk.Entry(self.setting_frame,width=25)
            tmp_speaker_list.insert(0,speaker_list_values[i])
            tmp_speaker_list.grid(row=2*i+1, column=1,sticky=W)

            #音量とスケールを置くためのフレーム
            tmp_frame=ttk.Frame(self.setting_frame)
            tmp_frame.grid(row=2*i+1, column=2)

            #音量バー
            tmp_detect_check=ttk.Progressbar(tmp_frame,length=240,orient=HORIZONTAL,mode='determinate',maximum=120)
            tmp_detect_check.grid(row=0, column=0)

            #音量バーの下にスケールを置く
            tmp_scale=ttk.Scale(tmp_frame,from_=0,to=120,orient=HORIZONTAL,length=240)
            tmp_scale.set(60)
            tmp_scale.grid(row=1, column=0)

            #削除ボタン
            tmp_del_button=ttk.Button(self.setting_frame,text='削除',command=functools.partial(self.DelChannel,i))
            tmp_del_button.grid(row=2*i+1, column=3)

            #セパレータ
            tmp_separator=ttk.Separator(self.setting_frame, orient="horizontal")
            tmp_separator.grid(row=2*i+2, columnspan=4, sticky=(W,E))

            #ハンドラに値追加
            device_list_handler.append(tmp_device_list)
            speaker_list_handler.append(tmp_speaker_list)
            detect_check_handler.append(tmp_detect_check)
            delete_button_handler.append(tmp_del_button)
            scale_handler.append(tmp_scale)
            container_handler.append(tmp_frame)
            separator_handler.append(tmp_separator)
        else:
            #追加ボタン
            self.ch_add_btn=ttk.Button(self.setting_frame,text='CH追加',command=self.AddChannel)
            self.ch_add_btn.grid(row=2*CH+1,column=3)

    #CSVエクスポート
    def Export(self):
        #csvにする
        fTyp=[('CSVファイル','*.csv')]
        cwd=os.getcwd()
        output=tkfd.asksaveasfilename(filetypes=fTyp,initialdir=cwd)
        if '.csv' not in output:
            output=output+'.csv'

        with open(output,'w') as f:
            writer=csv.writer(f, lineterminator='\n')
            for i in self.result_table.get_children():
                tmp=self.result_table.item(i)["values"]
                writer.writerow(tmp)

    #メインウィンドウを閉じる
    def quit(self):
        self.root.quit()

# In[4]:メイン関数
if __name__=='__main__':
    
    main=MainWindow()
    shutil.rmtree(FILEPATH)