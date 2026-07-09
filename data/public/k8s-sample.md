# Kubernetes 리소스 관계 샘플

Graph RAG 관계 탐색 데모용 공개 샘플 문서다.
"Deployment를 외부 통신하려면 어떻게 해야 하는가"라는 질문이
Deployment → Pod → Service-JS 관계 경로를 따라 답변되는지 확인하는 데 쓴다.

## Pod

Pod는 Kubernetes의 최소 배포 단위이다.
Pod는 하나 이상의 컨테이너를 포함한다.

## Deployment

Deployment는 Pod를 관리할 수 있다.
Deployment는 원하는 Pod 개수를 유지하고, Pod의 배포와 업데이트를 관리한다.

## Service

Service-JS는 Pod를 외부 통신 가능하도록 열어준다.
Service-JS는 Pod 앞에서 고정된 접근 지점을 제공한다.
