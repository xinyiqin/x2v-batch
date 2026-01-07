import os
from collections import defaultdict
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
from dotenv import load_dotenv

load_dotenv()


class User:
    @classmethod
    def format(cls, line):
        res = ''
        i = 0
        while i < len(line):
            if line[i:i + 2] == '\\u':
                res += bytes(line[i:i + 6], 'utf-8').decode('unicode_escape')
                i = i + 6
            else:
                res += line[i]
                i += 1
        return res

    def __init__(self, username: str, start_time: int, req_body, resp_body, status):
        self.username = username
        self.start_time = start_time
        self.start_date = datetime.fromtimestamp(start_time // 1000)

        req_body = req_body
        resp_body = resp_body
        stream = False
        self.data_status = None

        try:
            self.req_body = json.loads(req_body)
            if self.req_body.get('stream'):
                stream = True
            temp_req_body = self.req_body["messages"]
            res = []
            for tp in temp_req_body:
                res.append({
                    tp['role']: tp['content']
                })
            self.req_body = res
        except Exception as e:
            self.req_body = req_body

        try:
            if not stream:
                tmp_resp_body = json.loads(resp_body)
                self.data_status = tmp_resp_body['data']['status']
                self.resp_body = tmp_resp_body['data']['choices'][0]['message']
                self.session_id = tmp_resp_body['data']['id']
            else:
                res = resp_body.split('\n')
                res = [r for r in res if r != '']
                if len(res) == 1:
                    res = res[-1]
                else:
                    res = res[-2]
                res = json.loads(res[6:])
                self.data_status = res['data']['status']
                if len(res['data']['choices']) > 0:
                    self.resp_body = res['data']['choices'][0].get('message')
                    self.session_id = res['data']['id']
                else:
                    self.resp_body = resp_body
                    self.session_id = res['data']['id']

                if self.resp_body is None:
                    self.resp_body = ''
                    datas = resp_body.split('\n')
                    datas = [data for data in datas if data != '']
                    for data in datas[:-1]:
                        if data == '':
                            continue
                        res = json.loads(data[6:])
                        self.data_status = res['data']['status']
                        if len(res['data']['choices']) == 0:
                            continue
                        self.resp_body += res['data']['choices'][0]['delta']
                        self.session_id = res['data']['id']
        except Exception as e:
            self.resp_body = resp_body
            self.session_id = None

        self.status = status
        if self.data_status is None and self.status == 200 and resp_body != "None" and req_body != 'None':
            print()

    def __lt__(self, other):
        return self.start_time < other.start_time

    def to_list(self):
        return [self.username, self.start_date.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(self.req_body, ensure_ascii=False, indent=2), self.resp_body, self.status,
                self.data_status, '', '', '', '', self.session_id]


MAIL_SERVER = os.getenv('MAIL_SERVER')
MAIL_PORT = os.getenv('MAIL_PORT')
MAIL_USE_TLS = os.getenv('MAIL_USE_TLS') == "True"
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")
JSON_AS_ASCII = False


def send_email(date: datetime, user_emails: list,cc_user_emails:list):
    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as server:
            server.connect(MAIL_SERVER)
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            date_object = datetime.strptime(date, "%Y-%m-%d")
            date_string = date_object.strftime("%Y年%m月%d日")
            # date_string = date.strftime("%Y年%m月%d日")

            message = MIMEMultipart()
            message['From'] = MAIL_DEFAULT_SENDER
            message['To'] = ','.join(user_emails)
            message['Cc'] = ','.join(cc_user_emails)
            message['Subject'] = "To C后端数据飞轮报告 - 商量"  # 替换为您的邮件主题
            print(message)
            html_part = MIMEText(get_email(date_string), 'html')
            message.attach(html_part)
            server.sendmail(MAIL_DEFAULT_SENDER, user_emails + cc_user_emails, message.as_string())
    except Exception as e:
        print('邮件发送失败:', str(e))


def get_email(date):
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>To C后端数据飞轮报告 - 商量</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
        }
        .container {
            max-width: 600px;
            margin: 20px auto;
            background-color: #ffffff;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
        .header {
            background-color: #003366;
            color: white;
            text-align: center;
            padding: 10px 0;
        }
        .content {
            padding: 20px;
            color: #333333;
        }
        .content p {
            line-height: 1.6;
        }
        .content a {
            color: #003366;
            text-decoration: underline;
            font-weight: bold;
        }
        .content a:hover {
            text-decoration: underline;
        }
        .report {
            font-size: 16px;
            margin-top: 30px; /* 增加段前距离 */
            margin-bottom: 30px; /* 增加段后距离 */
        }
        .footer {
            background-color: #f4f4f4;
            text-align: center;
            padding: 10px;
            font-size: 12px;
            color: #777777;
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h2>To C后端数据飞轮报告 - 商量</h2>
    </div>
    <div class="content">
        <p>Hi all,</p>
        <p>%s数据飞轮报告已更新。</p>
        <p class="report">
            <a href="https://sensechat-yue.netlify.app/">sensechat-粤语数据报告</a>
        </p>
        <p class="report">
            <a href="https://sensechat.netlify.app/">sensechat-简中数据报告</a>
        </p>
        <p>如对报告或统计数据有问题，或有任何变动需求，请联系
            <a href="mailto:qinxinyi@sensetime.com">qinxinyi@sensetime.com</a>
        </p>
        <p>&nbsp;</p>
        <p>Thanks</p>
        <p>————————</p>
        <p>模型工具链团队</p>
    </div>
    <div class="footer">
        <p>© 2024 SenseTime - Large Model Tools System. </p>
        <p>All rights reserved.</p>
    </div>
</div>
</body>
</html>
 ''' % (date)

from collections import defaultdict
from datetime import datetime


if __name__ == "__main__":
    # 设置命令行参数解析
    import argparse
    parser = argparse.ArgumentParser(description='Process time parameters.')
    parser.add_argument('--date', type=str)
    args = parser.parse_args()
    # 示例添加用户：假设用户名为 'username1'
    user_emails=['qinxinyi@sensetime.com','gongruihao@sensetime.com','luoweichao@sensetime.com','zhangchen1@sensetime.com','liuxinyi1@sensetime.com']
    
    user_emails = [
        "gongruihao@sensetime.com",
        "daijuan@sensetime.com",
        "sunyunle@sensetime.com",
        "ivanli@sensetime.com",
        "yangyang6@sensetime.com",
        "lushaoqing@sensetime.com",
        "zhujinghua@sensetime.com",
        "gengduolun@sensetime.com",
        "moyan@sensetime.com",
        "tangyiting@sensetime.com",
        "xuyichen@sensetime.com",
        "wayne.zhang@sensetime.com",
        "chenyimin@sensetime.com",
        "xuyi@sensetime.com",
        "wangxinjiang@sensetime.com",
        "wangkaiqi@sensetime.com",
        "luotto@sensetime.com",
        "tianhao2@senseauto.com",
        "chenlei4@sensetime.com",
        "luojiapeng@sensetime.com",
        "caoyang@sensetime.com",
        "wuwencheng@sensetime.com",
        "linjunpeng@sensetime.com",
        "dana@sensetime.com",
        "heconghui@sensetime.com",
        "zhangchaobin@sensetime.com",
        "luoweichao@sensetime.com",
        "qinxinyi@sensetime.com",
        "zhangchen1@sensetime.com",
        "wangyusong@sensetime.com",
        "zhaozhangzong@sensetime.com",
        "sunwenxiu@sensetime.com",
        "leifei1@sensetime.com",
        "zhourong@sensetime.com",
        "zhangjunyu@sensetime.com",
        "libaoxiang@sensetime.com",
        "liuliang1@sensetime.com",
        "liuxinyi1@sensetime.com",
        "libotong@sensetime.com",
        "xujinglei@sensetime.com",
        "guodongyu@sensetime.com"
    ]

    cc_user_emails=[
        "dhlin@sensetime.com",
        "xg@sensetime.com",
        "xuli@sensetime.com",
        "wangyanhua@sensetime.com"]

    # user_emails=['qinxinyi@sensetime.com']
    # cc_user_emails=['qinxinyi@sensetime.com']
    # 设置邮件发送的日期
    send_date = args.date  # 或者您想要的任何日期

    # 调用 send_email 函数
    send_email(send_date, user_emails,cc_user_emails)
