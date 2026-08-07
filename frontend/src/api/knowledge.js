import api from './index'

export const listCourses = () => api.get('/knowledge/courses')
export const getCourseTree = (courseId) => api.get(`/knowledge/courses/${courseId}/tree`)
export const getKnowledgePoint = (pointId) => api.get(`/knowledge/points/${pointId}`)
export const getKnowledgePointLearning = (pointId) => api.get(`/knowledge/points/${pointId}/learning`)
