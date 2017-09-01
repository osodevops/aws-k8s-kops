FROM python:2.7.13-wheezy
ADD /app /app
ENV PYTHONPATH=/app
RUN apt-get update
RUN apt-get install unzip git -y
RUN wget https://github.com/kubernetes/kops/releases/download/1.7.0/kops-linux-amd64
RUN wget https://storage.googleapis.com/kubernetes-release/release/v1.7.0/bin/linux/amd64/kubectl
RUN wget https://releases.hashicorp.com/terraform/0.10.2/terraform_0.10.2_linux_amd64.zip
RUN chmod +x kops-linux-amd64
RUN chmod +x kubectl
RUN unzip terraform_0.10.2_linux_amd64.zip
RUN mv terraform /usr/local/bin/terraform
RUN mv kops-linux-amd64 /usr/local/bin/kops
RUN mv kubectl /usr/local/bin/kubectl
RUN mkdir /root/.ssh
ADD /app/config /root/.ssh/config
RUN pip install -r /app/requirements.txt